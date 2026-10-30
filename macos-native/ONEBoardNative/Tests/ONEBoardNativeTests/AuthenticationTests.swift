import Foundation
import XCTest
@testable import ONEBoardNative

private final class AuthenticationProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let verification = request.url?.path == "/api/auth/login"
        let body = verification
            ? #"{"ok":false,"verification_required":true,"error":"Verify your email"}"#
            : #"{"ok":false,"error":"Access denied"}"#
        let response = HTTPURLResponse(url: request.url!, statusCode: 403,
                                       httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class AuthenticationTests: XCTestCase {
    private func api() -> ONEBoardAPI {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AuthenticationProtocol.self]
        return ONEBoardAPI(session: URLSession(configuration: configuration))
    }

    func testUnverifiedLoginPreservesVerificationState() async throws {
        do {
            _ = try await api().login(email: "test@example.test", password: "password123")
            XCTFail("Unverified login must not succeed")
        } catch ONEBoardAPIError.verificationRequired(let message) {
            XCTAssertEqual(message, "Verify your email")
        }
    }

    func testOtherForbiddenResponsesRemainErrors() async throws {
        do {
            _ = try await api().sessionStatus()
            XCTFail("Forbidden response must not succeed")
        } catch ONEBoardAPIError.server(let message) {
            XCTAssertEqual(message, "Access denied")
        }
    }
}
