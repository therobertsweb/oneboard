import Foundation
import Security

private enum ONEBoardKeychain {
    private static let service = "com.oneboard.native.ai-credentials"
    private static let account = "default"

    static func load() -> [String: String] {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let values = try? JSONSerialization.jsonObject(with: data) as? [String: String]
        else {
            return [:]
        }
        return values
    }

    static func save(_ values: [String: String]) throws {
        let data = try JSONSerialization.data(withJSONObject: values)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attributes = [kSecValueData as String: data]
        let status = SecItemCopyMatching(query as CFDictionary, nil) == errSecSuccess
            ? SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
            : SecItemAdd((query.merging(attributes) { _, new in new }) as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw ONEBoardAPIError.server("Could not save AI credentials in the macOS Keychain.")
        }
    }
}

enum ONEBoardAPIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case nonJSONResponse(Int, String)
    case server(String)
    case verificationRequired(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            "Invalid ONEBoard API URL."
        case .invalidResponse:
            "ONEBoard returned an invalid response."
        case .nonJSONResponse(let status, let preview):
            "ONEBoard returned non-JSON data (HTTP \(status)): \(preview)"
        case .server(let message):
            message
        case .verificationRequired(let message):
            message
        }
    }
}

final class ONEBoardAPI: ObservableObject {
    static let shared = ONEBoardAPI()

    @Published var baseURL = URL(string: "http://127.0.0.1:5002")!
    var serviceToken = ""
    private var aiCredentials = ONEBoardKeychain.load()

    private let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func sessionStatus() async throws -> [String: Any] {
        try await request(path: "/api/session")
    }

    func login(email: String, password: String) async throws -> [String: Any] {
        try await request(
            path: "/api/auth/login",
            method: "POST",
            body: ["email": email, "password": password]
        )
    }

    func register(name: String, email: String, password: String, confirmPassword: String) async throws -> [String: Any] {
        try await request(
            path: "/api/auth/register",
            method: "POST",
            body: [
                "name": name,
                "email": email,
                "password": password,
                "confirm_password": confirmPassword
            ]
        )
    }

    func resendVerification(email: String) async throws -> [String: Any] {
        try await request(
            path: "/api/auth/resend-verification",
            method: "POST",
            body: ["email": email]
        )
    }

    func logout() async throws -> [String: Any] {
        try await request(path: "/api/auth/logout", method: "POST")
    }

    func dashboard() async throws -> [String: Any] {
        try await request(path: "/api/dashboard")
    }

    func createSearchConsoleConnection() async throws -> URL {
        let response = try await request(path: "/api/google-search-console/connect")
        guard let value = response["auth_url"] as? String, let url = URL(string: value) else {
            throw ONEBoardAPIError.invalidResponse
        }
        return url
    }

    func selectSearchConsoleSite(_ siteURL: String) async throws -> [String: Any] {
        try await request(
            path: "/api/google-search-console/site",
            method: "POST",
            body: ["site_url": siteURL]
        )
    }

    func disconnectSearchConsole() async throws -> [String: Any] {
        try await request(path: "/api/google-search-console/disconnect", method: "POST")
    }

    func siteManager(path: String = "") async throws -> [String: Any] {
        var components = URLComponents()
        components.path = "/api/site-manager"
        if !path.isEmpty {
            components.queryItems = [URLQueryItem(name: "path", value: path)]
        }
        guard let requestPath = components.string else {
            throw ONEBoardAPIError.invalidURL
        }
        return try await request(path: requestPath)
    }

    func connectSiteDirectory(_ path: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/connect",
            method: "POST",
            body: ["path": path]
        )
    }

    func saveRemoteConnection(
        host: String,
        port: String,
        username: String,
        remotePath: String,
        keyPath: String,
        authMethod: String,
        password: String,
        expectedDirectory: String
    ) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/remote",
            method: "POST",
            body: [
                "host": host,
                "port": port,
                "username": username,
                "remote_path": remotePath,
                "key_path": keyPath,
                "auth_method": authMethod,
                "password": password,
                "expected_directory_path": expectedDirectory
            ]
        )
    }

    func testRemoteConnection(
        host: String,
        port: String,
        username: String,
        remotePath: String,
        keyPath: String,
        authMethod: String,
        password: String,
        expectedDirectory: String
    ) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/remote/test",
            method: "POST",
            body: [
                "host": host,
                "port": port,
                "username": username,
                "remote_path": remotePath,
                "key_path": keyPath,
                "auth_method": authMethod,
                "password": password,
                "expected_directory_path": expectedDirectory
            ],
            timeout: 45
        )
    }

    func generateSSHKey() async throws -> [String: Any] {
        try await request(path: "/api/site-manager/ssh-key", method: "POST")
    }

    func syncRemoteSite(expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/remote/sync",
            method: "POST",
            body: ["expected_directory_path": expectedDirectory],
            timeout: 330
        )
    }

    func createBackup(expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/backup",
            method: "POST",
            body: ["expected_directory_path": expectedDirectory]
        )
    }

    func restoreBackup(id: Int, expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/restore",
            method: "POST",
            body: ["backup_id": id, "expected_directory_path": expectedDirectory]
        )
    }

    func runCodexUpdate(
        prompt: String,
        quickPrompt: String = "",
        selectedAsset: String = "",
        provider: String = "",
        model: String = "",
        expectedDirectory: String
    ) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/codex-update",
            method: "POST",
            body: [
                "prompt": prompt,
                "quick_prompt": quickPrompt,
                "selected_asset": selectedAsset,
                "provider": provider,
                "model": model,
                "expected_directory_path": expectedDirectory
            ],
            timeout: 330
        )
    }

    func createSearchConsolePage(
        title: String,
        keyword: String,
        expectedDirectory: String
    ) async throws -> [String: Any] {
        try await request(
            path: "/api/seo-suggestions/create",
            method: "POST",
            body: [
                "title": title,
                "keyword": keyword,
                "expected_directory_path": expectedDirectory,
            ],
            timeout: 330
        )
    }

    func uploadAsset(fileURL: URL, expectedDirectory: String) async throws -> [String: Any] {
        let attributes = try FileManager.default.attributesOfItem(atPath: fileURL.path)
        let size = (attributes[.size] as? NSNumber)?.int64Value ?? 0
        guard size > 0, size <= 20 * 1024 * 1024 else {
            throw ONEBoardAPIError.server("Images must be between 1 byte and 20 MB.")
        }
        guard let url = URL(string: "/api/site-manager/assets/upload", relativeTo: baseURL) else {
            throw ONEBoardAPIError.invalidURL
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        addServiceAuthentication(to: &request)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = try multipartBody(
            fieldName: "asset",
            fileURL: fileURL,
            fields: ["expected_directory_path": expectedDirectory],
            boundary: boundary
        )

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw ONEBoardAPIError.invalidResponse
        }
        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw ONEBoardAPIError.nonJSONResponse(httpResponse.statusCode, responsePreview(data))
        }
        guard let json = object as? [String: Any] else {
            throw ONEBoardAPIError.invalidResponse
        }
        if !(200..<300).contains(httpResponse.statusCode) {
            throw ONEBoardAPIError.server(json["error"] as? String ?? "ONEBoard asset upload failed.")
        }
        return json
    }

    func createSEOContent(title: String, keyword: String, tone: String, audience: String, cta: String, expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/seo-content",
            method: "POST",
            body: [
                "title": title,
                "keyword": keyword,
                "tone": tone,
                "audience": audience,
                "cta": cta,
                "expected_directory_path": expectedDirectory
            ],
            timeout: 330
        )
    }

    func updateAction(id: Int, action: String, expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/update/action",
            method: "POST",
            body: ["update_id": id, "action": action, "expected_directory_path": expectedDirectory],
            timeout: action == "publish" ? 600 : 60
        )
    }

    func deleteFile(path: String, expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/files/delete",
            method: "POST",
            body: ["path": path, "expected_directory_path": expectedDirectory]
        )
    }

    func runTerminal(command: String, expectedDirectory: String) async throws -> [String: Any] {
        try await request(
            path: "/api/site-manager/terminal/run",
            method: "POST",
            body: ["command": command, "expected_directory_path": expectedDirectory]
        )
    }

    func securityScanHistory() async throws -> [String: Any] {
        try await request(path: "/api/security-scan")
    }

    func runSecurityScan(domain: String) async throws -> [String: Any] {
        try await request(path: "/api/security-scan", method: "POST", body: ["domain": domain])
    }

    func settings() async throws -> [String: Any] {
        try await request(path: "/api/settings")
    }

    func saveAccount(
        name: String,
        companyName: String,
        companyEmail: String,
        companyWebsite: String,
        currentPassword: String,
        newPassword: String,
        confirmPassword: String
    ) async throws -> [String: Any] {
        try await request(
            path: "/api/settings/account",
            method: "POST",
            body: [
                "name": name,
                "company_name": companyName,
                "company_email": companyEmail,
                "company_website": companyWebsite,
                "current_password": currentPassword,
                "new_password": newPassword,
                "confirm_password": confirmPassword,
            ]
        )
    }

    func aiProviders() async throws -> [String: Any] {
        try await request(path: "/api/ai/providers")
    }

    func aiSettings() async throws -> [String: Any] {
        try await request(path: "/api/settings/ai")
    }

    func aiRuns() async throws -> [String: Any] {
        try await request(path: "/api/ai/runs")
    }

    func runAI(taskType: String, provider: String, model: String, prompt: String, context: String = "") async throws -> [String: Any] {
        try await request(
            path: "/api/ai/run",
            method: "POST",
            body: [
                "task_type": taskType,
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "context": context
            ],
            timeout: 180
        )
    }

    func saveOpenAIKey(_ apiKey: String, currentPassword: String) async throws -> [String: Any] {
        try await request(
            path: "/api/settings/openai",
            method: "POST",
            body: [
                "openai_api_key": apiKey,
                "current_password": currentPassword
            ]
        )
    }

    func saveAICredentials(
        currentPassword: String,
        openAIKey: String,
        anthropicKey: String,
        openRouterKey: String,
        googleKey: String
    ) async throws -> [String: Any] {
        aiCredentials = [
            "openai": openAIKey,
            "anthropic": anthropicKey,
            "openrouter": openRouterKey,
            "google": googleKey,
        ].filter { !$0.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        try ONEBoardKeychain.save(aiCredentials)
        return try await request(
            path: "/api/settings/ai-credentials",
            method: "POST",
            body: [
                "current_password": currentPassword,
                "openai_api_key": openAIKey,
                "anthropic_api_key": anthropicKey,
                "openrouter_api_key": openRouterKey,
                "google_api_key": googleKey
            ]
        )
    }

    func saveAIPolicy(provider: String, model: String) async throws -> [String: Any] {
        try await request(
            path: "/api/settings/ai-policy",
            method: "POST",
            body: ["provider": provider, "model": model]
        )
    }

    private func request(
        path: String,
        method: String = "GET",
        body: [String: Any]? = nil,
        timeout: TimeInterval = 60
    ) async throws -> [String: Any] {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw ONEBoardAPIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        addServiceAuthentication(to: &request)

        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw ONEBoardAPIError.invalidResponse
        }

        let object: Any
        do {
            object = try JSONSerialization.jsonObject(with: data)
        } catch {
            throw ONEBoardAPIError.nonJSONResponse(httpResponse.statusCode, responsePreview(data))
        }
        guard let json = object as? [String: Any] else {
            throw ONEBoardAPIError.invalidResponse
        }

        if httpResponse.statusCode == 403, json["verification_required"] as? Bool == true {
            throw ONEBoardAPIError.verificationRequired(json["error"] as? String ?? "Verify your email before signing in.")
        }
        if !(200..<300).contains(httpResponse.statusCode) {
            throw ONEBoardAPIError.server(json["error"] as? String ?? "ONEBoard API request failed.")
        }

        return json
    }

    private func addServiceAuthentication(to request: inout URLRequest) {
        if !serviceToken.isEmpty {
            request.setValue(serviceToken, forHTTPHeaderField: "X-ONEBoard-Service-Token")
        }
        if !aiCredentials.isEmpty,
           let data = try? JSONSerialization.data(withJSONObject: aiCredentials) {
            request.setValue(data.base64EncodedString(), forHTTPHeaderField: "X-ONEBoard-AI-Credentials")
        }
    }

    private func multipartBody(fieldName: String, fileURL: URL, fields: [String: String], boundary: String) throws -> Data {
        var data = Data()
        let filename = fileURL.lastPathComponent
        let mimeType = mimeType(for: fileURL)
        let fileData = try Data(contentsOf: fileURL)

        for (name, value) in fields {
            data.append("--\(boundary)\r\n".data(using: .utf8)!)
            data.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            data.append("\(value)\r\n".data(using: .utf8)!)
        }

        data.append("--\(boundary)\r\n".data(using: .utf8)!)
        data.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        data.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        data.append(fileData)
        data.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        return data
    }

    private func mimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "jpg", "jpeg":
            "image/jpeg"
        case "png":
            "image/png"
        case "gif":
            "image/gif"
        case "webp":
            "image/webp"
        default:
            "application/octet-stream"
        }
    }

    private func responsePreview(_ data: Data) -> String {
        let text = String(data: data, encoding: .utf8) ?? "<binary response>"
        let cleaned = text.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        return String(cleaned.prefix(180))
    }
}
