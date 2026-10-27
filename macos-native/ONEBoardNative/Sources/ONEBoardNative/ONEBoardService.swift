import AppKit
import Foundation

@MainActor
final class ONEBoardService: ObservableObject {
    @Published var status = "Service not started"
    @Published var error = ""

    private var process: Process?
    private var logHandle: FileHandle?
    private var port = 51249
    private let serviceToken = UUID().uuidString + UUID().uuidString
    private var terminationObserver: NSObjectProtocol?

    private struct LaunchConfiguration {
        let executable: URL
        let arguments: [String]
        let workingDirectory: URL
    }

    private enum ProbeResult {
        case api
        case occupied(String)
        case unavailable
    }

    init() {
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.stop()
            }
        }
    }

    deinit {
        if let terminationObserver {
            NotificationCenter.default.removeObserver(terminationObserver)
        }
        if process?.isRunning == true {
            process?.terminate()
        }
        try? logHandle?.close()
    }

    func ensureRunning() async {
        if process?.isRunning == true, case .api = await probeService(port: port) {
            configureAPI(port: port)
            status = "ONEBoard service running"
            error = ""
            return
        }

        let preferredPort = Int(ProcessInfo.processInfo.environment["ONEBOARD_SERVICE_PORT"] ?? "") ?? 51249
        let candidates = [preferredPort] + (51249...51259).filter { $0 != preferredPort }

        for candidate in candidates {
            switch await probeService(port: candidate) {
            case .api:
                port = candidate
                configureAPI(port: candidate)
                status = "ONEBoard service running"
                error = ""
                return
            case .occupied:
                continue
            case .unavailable:
                port = candidate
                configureAPI(port: candidate)
                guard startLocalService(port: candidate) else { return }

                for _ in 0..<30 {
                    try? await Task.sleep(nanoseconds: 200_000_000)
                    if case .api = await probeService(port: candidate) {
                        status = "ONEBoard service running"
                        error = ""
                        return
                    }
                    if process?.isRunning != true {
                        break
                    }
                }

                stop()
            }
        }

        status = "ONEBoard service unavailable"
        if error.isEmpty {
            error = "Could not start the private ONEBoard service."
        }
    }

    func stop() {
        if process?.isRunning == true {
            process?.terminate()
        }
        process = nil
        try? logHandle?.close()
        logHandle = nil
        status = "Service stopped"
    }

    private func configureAPI(port: Int) {
        ONEBoardAPI.shared.baseURL = URL(string: "http://127.0.0.1:\(port)")!
        ONEBoardAPI.shared.serviceToken = serviceToken
    }

    private func probeService(port: Int) async -> ProbeResult {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/session") else {
            return .unavailable
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 0.7
        request.setValue(serviceToken, forHTTPHeaderField: "X-ONEBoard-Service-Token")

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                return .unavailable
            }
            if [200, 401].contains(http.statusCode), isONEBoardResponse(data) {
                return .api
            }
            return .occupied("Another service is using local port \(port).")
        } catch {
            return .unavailable
        }
    }

    private func isONEBoardResponse(_ data: Data) -> Bool {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return false
        }
        return json["ok"] != nil && json["authenticated"] != nil
    }

    @discardableResult
    private func startLocalService(port: Int) -> Bool {
        guard process == nil else { return true }
        guard let launch = launchConfiguration() else {
            status = "ONEBoard service is missing"
            error = "Rebuild the native app so its private service is included."
            return false
        }

        let dataDirectory: URL
        do {
            dataDirectory = try applicationDataDirectory()
        } catch {
            status = "Could not prepare ONEBoard data"
            self.error = error.localizedDescription
            return false
        }

        let logURL = dataDirectory.appendingPathComponent("service.log")
        rotateLogIfNeeded(at: logURL)
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }
        logHandle = try? FileHandle(forWritingTo: logURL)
        _ = try? logHandle?.seekToEnd()

        let process = Process()
        process.executableURL = launch.executable
        process.arguments = launch.arguments
        process.currentDirectoryURL = launch.workingDirectory
        process.environment = serviceEnvironment(dataDirectory: dataDirectory, port: port)
        process.standardOutput = logHandle
        process.standardError = logHandle
        process.terminationHandler = { [weak self] terminatedProcess in
            Task { @MainActor [weak self] in
                guard let self, self.process === terminatedProcess else { return }
                self.process = nil
                try? self.logHandle?.close()
                self.logHandle = nil
                if terminatedProcess.terminationStatus != 0 {
                    self.status = "ONEBoard service stopped"
                    self.error = "The local service exited with code \(terminatedProcess.terminationStatus). See service.log in Application Support/ONEBoard."
                }
            }
        }

        do {
            try process.run()
            self.process = process
            status = "Starting ONEBoard service"
            error = ""
            return true
        } catch {
            status = "Could not start service"
            self.error = error.localizedDescription
            try? logHandle?.close()
            logHandle = nil
            return false
        }
    }

    private func launchConfiguration() -> LaunchConfiguration? {
        if let resources = Bundle.main.resourceURL {
            let helper = resources.appendingPathComponent("service/ONEBoardService")
            if FileManager.default.isExecutableFile(atPath: helper.path) {
                return LaunchConfiguration(
                    executable: helper,
                    arguments: [],
                    workingDirectory: helper.deletingLastPathComponent()
                )
            }
        }

        guard let root = developmentServiceRoot() else { return nil }
        let pythonCandidates = [
            root.appendingPathComponent("myproject/env/bin/python"),
            root.appendingPathComponent(".venv/bin/python"),
            root.appendingPathComponent("venv/bin/python"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/local/bin/python3"),
            URL(fileURLWithPath: "/usr/bin/python3")
        ]
        guard let python = pythonCandidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else {
            return nil
        }
        let script = root.appendingPathComponent("run_waitress.py")
        guard FileManager.default.fileExists(atPath: script.path) else { return nil }
        return LaunchConfiguration(executable: python, arguments: [script.path], workingDirectory: root)
    }

    private func developmentServiceRoot() -> URL? {
        if let configured = ProcessInfo.processInfo.environment["ONEBOARD_SERVICE_ROOT"], !configured.isEmpty {
            let url = URL(fileURLWithPath: configured, isDirectory: true)
            if FileManager.default.fileExists(atPath: url.appendingPathComponent("app.py").path) {
                return url
            }
        }

        var sourceURL = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 {
            sourceURL.deleteLastPathComponent()
        }
        if FileManager.default.fileExists(atPath: sourceURL.appendingPathComponent("app.py").path) {
            return sourceURL
        }
        return nil
    }

    private func applicationDataDirectory() throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        let directory = base.appendingPathComponent("ONEBoard", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let exampleTarget = directory.appendingPathComponent(".env.example")
        if !FileManager.default.fileExists(atPath: exampleTarget.path),
           let resources = Bundle.main.resourceURL {
            let bundledExample = resources.appendingPathComponent("service/.env.example")
            if FileManager.default.fileExists(atPath: bundledExample.path) {
                try? FileManager.default.copyItem(at: bundledExample, to: exampleTarget)
            }
        }
        return directory
    }

    private func serviceEnvironment(dataDirectory: URL, port: Int) -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        environment["HOST"] = "127.0.0.1"
        environment["PORT"] = String(port)
        environment["ONEBOARD_DATA_DIR"] = dataDirectory.path
        environment["ONEBOARD_SERVICE_TOKEN"] = serviceToken
        environment["PYTHONUNBUFFERED"] = "1"
        let standardPaths = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        let currentPath = environment["PATH"] ?? ""
        environment["PATH"] = currentPath.isEmpty ? standardPaths : "\(currentPath):\(standardPaths)"
        return environment
    }

    private func rotateLogIfNeeded(at url: URL) {
        let maximumSize = 5 * 1024 * 1024
        guard
            let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
            let size = attributes[.size] as? NSNumber,
            size.intValue >= maximumSize
        else {
            return
        }

        let previousURL = url.appendingPathExtension("1")
        try? FileManager.default.removeItem(at: previousURL)
        try? FileManager.default.moveItem(at: url, to: previousURL)
    }
}
