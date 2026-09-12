//! Synthetic-only integration test injected into codex-app-server/tests.
//! No App Server, auth manager, worker, or model is started.
use codex_http_client::{ClientRouteClass, HttpClientBuilder, HttpClientFactory, OutboundProxyPolicy, RouteAwareClientPool};
use codex_state::{log_db, LogQuery, SqliteConfig, StateRuntime};
use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::Path;
use std::time::Duration;
use tracing_subscriber::prelude::*;

fn markers(seed: &str) -> Vec<String> {
    vec![format!("eyJhbGciOiJub25lIn0.{seed}.SYNTHETIC_SIGNATURE"),
         format!("SYNTH_COOKIE_{seed}"), format!("SYNTH_AUTH_{seed}"),
         format!("SYNTH_NORMAL_{seed}")]
}

fn scan_files(path: &Path, needles: &[String]) -> Result<usize, ()> {
    let mut count = 0;
    for item in std::fs::read_dir(path).map_err(|_| ())? {
        let entry = item.map_err(|_| ())?;
        let kind = entry.file_type().map_err(|_| ())?;
        if kind.is_symlink() { return Err(()); }
        if kind.is_dir() { count += scan_files(&entry.path(), needles)?; }
        else if kind.is_file() {
            let bytes = std::fs::read(entry.path()).map_err(|_| ())?;
            for needle in needles {
                let utf16: Vec<u8> = needle.encode_utf16().flat_map(u16::to_le_bytes).collect();
                if bytes.windows(needle.len()).any(|w| w == needle.as_bytes()) || bytes.windows(utf16.len()).any(|w| w == utf16) { return Err(()); }
            }
            count += 1;
        }
    }
    Ok(count)
}

async fn exercise() -> Result<(), ()> {
    let root = std::path::PathBuf::from(std::env::var_os("SAFE_LOGGING_ROOT").ok_or(())?);
    if !root.is_absolute() || !root.join(".synthetic-only").is_file() { return Err(()); }
    let seed = std::env::var("SAFE_LOGGING_SEED").map_err(|_| ())?;
    if seed.len() != 32 || !seed.bytes().all(|b| b.is_ascii_hexdigit()) { return Err(()); }
    let values = markers(&seed);
    let db_root = root.join("db");
    std::fs::create_dir(&db_root).map_err(|_| ())?;
    let config = SqliteConfig::from_sqlite_home(db_root.clone().try_into().map_err(|_| ())?);
    let state = StateRuntime::init(config, "synthetic".into()).await.map_err(|_| ())?;
    let layer = log_db::start(state.clone());
    let file = std::fs::File::create(root.join("test.log")).map_err(|_| ())?;
    let subscriber = tracing_subscriber::registry()
        .with(layer.clone().with_filter(log_db::default_filter()))
        .with(tracing_subscriber::fmt::layer().with_ansi(false).with_writer(std::sync::Mutex::new(file)))
        .with(tracing_subscriber::fmt::layer().with_ansi(false).with_writer(std::io::stderr));
    tracing::subscriber::set_global_default(subscriber).map_err(|_| ())?;

    for route_aware in [false, true] {
        let listener = TcpListener::bind("127.0.0.1:0").map_err(|_| ())?;
        listener.set_nonblocking(true).map_err(|_| ())?;
        let address = listener.local_addr().map_err(|_| ())?;
        let response = format!("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\nSet-Cookie: synthetic_jwt={}; Path=/\r\nSet-Cookie: synthetic_other={}; Path=/\r\nAuthorization: Bearer {}\r\nX-Synthetic-Normal: {}\r\nContent-Type: text/plain\r\n\r\nOK", values[0], values[1], values[2], values[3]);
        let server = std::thread::spawn(move || -> Result<(), ()> {
            let until = std::time::Instant::now() + Duration::from_secs(10);
            let mut socket = loop {
                match listener.accept() {
                    Ok((stream, peer)) => { if !peer.ip().is_loopback() { return Err(()); } break stream; }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock && std::time::Instant::now() < until => std::thread::sleep(Duration::from_millis(10)),
                    Err(_) => return Err(()),
                }
            };
            socket.set_read_timeout(Some(Duration::from_secs(5))).map_err(|_| ())?;
            socket.set_write_timeout(Some(Duration::from_secs(5))).map_err(|_| ())?;
            let mut request = Vec::new();
            let mut part = [0_u8; 1024];
            while !request.ends_with(b"\r\n\r\n") {
                let n = socket.read(&mut part).map_err(|_| ())?;
                if n == 0 || request.len() + n > 8192 { return Err(()); }
                request.extend_from_slice(&part[..n]);
            }
            socket.write_all(response.as_bytes()).map_err(|_| ())?;
            Ok(())
        });
        let url = format!("http://{address}/synthetic");
        let response = if route_aware {
            RouteAwareClientPool::new_without_redirects(HttpClientFactory::new(OutboundProxyPolicy::ReqwestDefault), ClientRouteClass::Other)
                .get(&url).timeout(Duration::from_secs(10)).send().await.map_err(|_| ())?
        } else {
            HttpClientBuilder::new().without_redirects().build_direct().map_err(|_| ())?
                .get(&url).timeout(Duration::from_secs(10)).send().await.map_err(|_| ())?
        };
        if response.status().as_u16() != 200 || format!("{:?}", response.version()) != "HTTP/1.1" { return Err(()); }
        // Prove headers are still delivered unchanged to the caller; never format their values.
        if response.headers().get_all("set-cookie").iter().count() != 2 { return Err(()); }
        if response.headers().get("authorization").and_then(|v| v.to_str().ok()) != Some(format!("Bearer {}", values[2]).as_str()) { return Err(()); }
        if response.text().await.map_err(|_| ())? != "OK" { return Err(()); }
        server.join().map_err(|_| ())??;
    }
    layer.flush().await;
    let rows = state.query_logs(&LogQuery { include_threadless: true, limit: Some(10000), ..Default::default() }).await.map_err(|_| ())?;
    let events: Vec<_> = rows.iter().filter(|r| r.target == "codex_http_client::client" && r.message.as_deref().is_some_and(|m| m.contains("Request completed"))).collect();
    if events.len() != 2 { return Err(()); }
    for row in events {
        let text = row.message.as_deref().ok_or(())?;
        if !text.contains("method=GET") || !text.contains("status=200") || !text.contains("version=HTTP/1.1") { return Err(()); }
        if values.iter().any(|v| text.contains(v)) { return Err(()); }
    }
    // Require WAL and SHM coverage before close/checkpoint could remove them.
    for suffix in ["", "-wal", "-shm"] {
        if !db_root.join(format!("logs_2.sqlite{suffix}")).is_file() { return Err(()); }
    }
    let before = scan_files(&root, &values)?;
    state.close().await;
    let after = scan_files(&root, &values)?;
    let summary = serde_json::json!({"http_requests":2,"request_completed_events":2,"wal_shm_checked":true,"files_before_close":before,"files_after_close":after,"secret_matches":0});
    std::fs::write(root.join("summary.json"), serde_json::to_vec(&summary).map_err(|_| ())?).map_err(|_| ())?;
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn worker_safe_logging() {
    assert!(tokio::time::timeout(Duration::from_secs(60), exercise()).await.is_ok_and(|r| r.is_ok()), "SYNTHETIC_LOGGING_CHECK_FAILED");
}
