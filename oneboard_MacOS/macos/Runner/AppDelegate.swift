import Cocoa
import FlutterMacOS
import Foundation

@main
class AppDelegate: FlutterAppDelegate {
  private let serviceToken = UUID().uuidString + UUID().uuidString
  private var serviceProcess: Process?
  private var serviceLog: FileHandle?
  private var servicePort: Int?

  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    return true
  }

  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }

  override func applicationWillTerminate(_ notification: Notification) {
    if serviceProcess?.isRunning == true {
      serviceProcess?.terminate()
    }
    try? serviceLog?.close()
  }

  func startONEBoardService() async throws -> [String: String] {
    if let process = serviceProcess, process.isRunning, let port = servicePort {
      return ["baseUrl": "http://127.0.0.1:\(port)", "token": serviceToken]
    }

    let dataDirectory = try FileManager.default.url(
      for: .applicationSupportDirectory,
      in: .userDomainMask,
      appropriateFor: nil,
      create: true
    ).appendingPathComponent("ONEBoard", isDirectory: true)
    try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)

    let portFile = dataDirectory.appendingPathComponent("service-port")
    let savedPort = (try? String(contentsOf: portFile, encoding: .utf8))
      .flatMap { Int($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
    // Google OAuth requires an exact redirect URI. Keep the native callback
    // port stable instead of silently switching to a random port when another
    // stale ONEBoard process is still running.
    let nativePort = Int(ProcessInfo.processInfo.environment["ONEBOARD_NATIVE_PORT"] ?? "51249") ?? 51249
    let candidatePorts = [nativePort]

    guard let launch = serviceLaunchConfiguration() else {
      throw NSError(domain: "ONEBoard", code: 1, userInfo: [NSLocalizedDescriptionKey: "The ONEBoard service could not be found in the app bundle."])
    }

    for port in candidatePorts {
      if await isPortBusy(port: port) {
        throw NSError(domain: "ONEBoard", code: 3, userInfo: [NSLocalizedDescriptionKey: "Another ONEBoard service is already using port \(port), possibly from an Xcode run or a copy that did not quit cleanly. Quit other ONEBoard copies and press Retry."])
      }
      let process = Process()
      process.executableURL = launch.executable
      process.arguments = launch.arguments
      process.currentDirectoryURL = launch.directory
      var environment = ProcessInfo.processInfo.environment
      environment["HOST"] = "127.0.0.1"
      environment["PORT"] = String(port)
      environment["ONEBOARD_SERVICE_PORT"] = String(port)
      environment["ONEBOARD_SERVICE_TOKEN"] = serviceToken
      environment["ONEBOARD_DATA_DIR"] = dataDirectory.path
      // Verification links must resolve to this Mac and its private database.
      environment["ONEBOARD_PUBLIC_URL"] = ""
      environment["PYTHONUNBUFFERED"] = "1"
      process.environment = environment

      let logURL = dataDirectory.appendingPathComponent("service.log")
      if !FileManager.default.fileExists(atPath: logURL.path) {
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
      }
      let log = try? FileHandle(forWritingTo: logURL)
      try? log?.seekToEnd()
      process.standardOutput = log
      process.standardError = log

      do {
        try process.run()
      } catch {
        try? log?.close()
        continue
      }
      serviceProcess = process
      serviceLog = log

      for _ in 0..<40 {
        try? await Task.sleep(nanoseconds: 200_000_000)
        if await isONEBoardRunning(port: port) {
          servicePort = port
          try? "\(port)\n".write(to: portFile, atomically: true, encoding: .utf8)
          return ["baseUrl": "http://127.0.0.1:\(port)", "token": serviceToken]
        }
        if !process.isRunning { break }
      }
      if process.isRunning { process.terminate() }
      serviceProcess = nil
      servicePort = nil
      try? serviceLog?.close()
      serviceLog = nil
    }

    throw NSError(domain: "ONEBoard", code: 2, userInfo: [NSLocalizedDescriptionKey: "ONEBoard could not start. Check service.log in Application Support/ONEBoard."])
  }

  func openExternalURL(_ value: String) -> Bool {
    guard let url = URL(string: value), ["http", "https"].contains(url.scheme?.lowercased() ?? "") else {
      return false
    }
    return NSWorkspace.shared.open(url)
  }

  func chooseFile() -> String? {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.prompt = "Choose"
    return panel.runModal() == .OK ? panel.url?.path : nil
  }

  func chooseDirectory() -> String? {
    let panel = NSOpenPanel()
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    panel.prompt = "Choose Folder"
    return panel.runModal() == .OK ? panel.url?.path : nil
  }

  /// True when ANYTHING answers the health endpoint, even with a foreign
  /// token. Our own fresh process is not running yet at this point, so any
  /// answer means a stale or foreign service holds the port.
  private func isPortBusy(port: Int) async -> Bool {
    guard let url = URL(string: "http://127.0.0.1:\(port)/api/session") else { return false }
    var request = URLRequest(url: url)
    request.timeoutInterval = 1
    do {
      let (_, response) = try await URLSession.shared.data(for: request)
      return response is HTTPURLResponse
    } catch {
      return false
    }
  }

  private func isONEBoardRunning(port: Int) async -> Bool {
    guard let url = URL(string: "http://127.0.0.1:\(port)/api/session") else { return false }
    var request = URLRequest(url: url)
    request.timeoutInterval = 1
    request.setValue(serviceToken, forHTTPHeaderField: "X-ONEBoard-Service-Token")
    do {
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse,
            [200, 401].contains(http.statusCode),
            let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
      return payload["authenticated"] != nil
    } catch {
      return false
    }
  }

  private func serviceLaunchConfiguration() -> (executable: URL, arguments: [String], directory: URL)? {
    if let resources = Bundle.main.resourceURL {
      let helper = resources.appendingPathComponent("service/ONEBoardService")
      if FileManager.default.isExecutableFile(atPath: helper.path) {
        return (helper, [], helper.deletingLastPathComponent())
      }
    }

    guard let root = developmentServiceRoot() else { return nil }
    let script = root.appendingPathComponent("oneboard_native_service.py")
    guard FileManager.default.fileExists(atPath: script.path) else { return nil }
    let candidates = [
      root.appendingPathComponent(".build-tools/macos-packager/bin/python"),
      root.appendingPathComponent(".build-tools/macos-packager/bin/python3"),
      root.appendingPathComponent(".venv/bin/python3"),
      root.appendingPathComponent("env/bin/python3"),
      URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
      URL(fileURLWithPath: "/usr/local/bin/python3"),
      URL(fileURLWithPath: "/usr/bin/python3"),
    ]
    guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else { return nil }
    return (python, [script.path], root)
  }

  private func developmentServiceRoot() -> URL? {
    var startingPoints = [URL]()
    if let configured = ProcessInfo.processInfo.environment["ONEBOARD_SERVICE_ROOT"] {
      startingPoints.append(URL(fileURLWithPath: configured, isDirectory: true))
    }
    startingPoints.append(URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true))
    if let resources = Bundle.main.resourceURL {
      startingPoints.append(resources)
    }
    // Xcode does not guarantee the app's working directory. During development,
    // use this source file's location as a stable anchor to the repository.
    startingPoints.append(URL(fileURLWithPath: #filePath).deletingLastPathComponent())

    for startingPoint in startingPoints {
      var candidate = startingPoint.standardizedFileURL
      for _ in 0..<14 {
        if FileManager.default.fileExists(atPath: candidate.appendingPathComponent("oneboard_native_service.py").path) {
          return candidate
        }
        let parent = candidate.deletingLastPathComponent()
        if parent.path == candidate.path { break }
        candidate = parent
      }
    }
    return nil
  }
}
