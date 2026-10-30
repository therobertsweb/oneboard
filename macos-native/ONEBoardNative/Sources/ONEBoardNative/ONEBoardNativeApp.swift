import SwiftUI
import AppKit
import UniformTypeIdentifiers
import UserNotifications

enum ONEBoardTheme {
    static let bgTop = Color(red: 2 / 255, green: 10 / 255, blue: 31 / 255)
    static let bgMid = Color(red: 3 / 255, green: 28 / 255, blue: 59 / 255)
    static let bgBottom = Color(red: 2 / 255, green: 57 / 255, blue: 94 / 255)
    static let sidebarTop = Color(red: 2 / 255, green: 12 / 255, blue: 39 / 255)
    static let sidebarBottom = Color(red: 2 / 255, green: 20 / 255, blue: 52 / 255)
    static let ink = Color(red: 239 / 255, green: 249 / 255, blue: 1)
    static let muted = Color(red: 165 / 255, green: 197 / 255, blue: 222 / 255)
    static let faint = Color(red: 111 / 255, green: 157 / 255, blue: 191 / 255)
    static let line = Color(red: 119 / 255, green: 211 / 255, blue: 1).opacity(0.20)
    static let brand = Color(red: 0 / 255, green: 205 / 255, blue: 1)
    static let brandDark = Color(red: 0 / 255, green: 104 / 255, blue: 234 / 255)
    static let success = Color(red: 20 / 255, green: 232 / 255, blue: 184 / 255)
    static let warning = Color(red: 1, green: 209 / 255, blue: 58 / 255)
    static let violet = Color(red: 100 / 255, green: 116 / 255, blue: 1)
    static let surface = Color(red: 22 / 255, green: 61 / 255, blue: 101 / 255).opacity(0.64)
    static let surfaceStrong = Color(red: 10 / 255, green: 36 / 255, blue: 75 / 255).opacity(0.90)
    static let surfaceHighlight = Color(red: 76 / 255, green: 139 / 255, blue: 191 / 255).opacity(0.22)
}

struct ONEBoardBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [ONEBoardTheme.bgTop, ONEBoardTheme.bgMid, ONEBoardTheme.bgBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Circle()
                .fill(ONEBoardTheme.brand.opacity(0.16))
                .frame(width: 620, height: 620)
                .blur(radius: 110)
                .offset(x: -470, y: -390)
            Circle()
                .fill(ONEBoardTheme.brandDark.opacity(0.28))
                .frame(width: 700, height: 700)
                .blur(radius: 130)
                .offset(x: 530, y: -420)
            Circle()
                .fill(ONEBoardTheme.success.opacity(0.09))
                .frame(width: 520, height: 520)
                .blur(radius: 120)
                .offset(x: 420, y: 430)
            LinearGradient(
                colors: [Color.white.opacity(0.035), .clear, Color.black.opacity(0.12)],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
    }
}

private struct ONEBoardGlassModifier: ViewModifier {
    let cornerRadius: CGFloat
    let strong: Bool

    func body(content: Content) -> some View {
        content
            .background {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: strong
                                ? [ONEBoardTheme.surfaceStrong, ONEBoardTheme.surface]
                                : [ONEBoardTheme.surfaceHighlight, ONEBoardTheme.surface],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            }
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(
                        LinearGradient(
                            colors: [Color.white.opacity(0.28), ONEBoardTheme.brand.opacity(0.22), Color.white.opacity(0.07)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
                    .allowsHitTesting(false)
            }
            .shadow(color: Color.black.opacity(0.24), radius: 22, x: 0, y: 14)
            .shadow(color: ONEBoardTheme.brand.opacity(0.05), radius: 18, x: 0, y: 0)
    }
}

private extension View {
    func oneBoardGlass(cornerRadius: CGFloat = 20, strong: Bool = false) -> some View {
        modifier(ONEBoardGlassModifier(cornerRadius: cornerRadius, strong: strong))
    }
}

@main
struct ONEBoardNativeApp: App {
    @StateObject private var appState = AppState()
    @StateObject private var service = ONEBoardService()

    var body: some Scene {
        Window("ONEBoard", id: "main") {
            AppEntryView()
                .environmentObject(appState)
                .environmentObject(service)
                .frame(minWidth: 960, minHeight: 640)
                .preferredColorScheme(.dark)
                .task {
                    await service.ensureRunning()
                    appState.apiStatus = service.status
                    appState.lastAPIError = service.error
                    await checkSession()
                }
        }
        .commands {
            SidebarCommands()
        }
        .defaultSize(width: 1240, height: 790)
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
    }

    @MainActor
    private func checkSession() async {
        do {
            let response = try await ONEBoardAPI.shared.sessionStatus()
            appState.authenticated = response["authenticated"] as? Bool ?? false
            if let user = response["user"] as? [String: Any] {
                appState.userName = user["name"] as? String ?? ""
                appState.openAIKeySaved = user["openai_api_key_configured"] as? Bool ?? false
            }
        } catch {
            appState.authenticated = false
        }
    }
}

enum ProcessNotificationKind {
    case success
    case failure

    var systemImage: String {
        switch self {
        case .success: "checkmark.circle.fill"
        case .failure: "exclamationmark.triangle.fill"
        }
    }

    var color: Color {
        switch self {
        case .success: ONEBoardTheme.success
        case .failure: ONEBoardTheme.warning
        }
    }
}

struct ProcessNotification: Identifiable {
    let id = UUID()
    let kind: ProcessNotificationKind
    let title: String
    let message: String
}

@MainActor
final class AppState: ObservableObject {
    @Published var selectedSection: AppSection = .dashboard
    @Published var authenticated = false
    @Published var userName = ""
    @Published var openAIKeySaved = false
    @Published var connectedDirectory = ""
    @Published var siteManagerDirectoryTransition = false
    @Published var siteManagerOperationInProgress = false
    @Published var remoteHost = ""
    @Published var remoteAuthMethod: RemoteAuthMethod = .sshKey
    @Published var apiStatus = "Not connected"
    @Published var lastAPIError = ""
    @Published var processNotification: ProcessNotification?

    private var notificationDismissTask: Task<Void, Never>?

    func notifyProcess(
        title: String,
        message: String,
        kind: ProcessNotificationKind = .success
    ) {
        notificationDismissTask?.cancel()
        let notification = ProcessNotification(kind: kind, title: title, message: message)
        processNotification = notification

        notificationDismissTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(9))
            guard !Task.isCancelled, self?.processNotification?.id == notification.id else { return }
            self?.processNotification = nil
        }

        Task {
            await Self.sendSystemNotification(title: title, body: message)
        }
    }

    func dismissProcessNotification() {
        notificationDismissTask?.cancel()
        processNotification = nil
    }

    private static func sendSystemNotification(title: String, body: String) async {
        let center = UNUserNotificationCenter.current()
        let settings = await withCheckedContinuation { continuation in
            center.getNotificationSettings { continuation.resume(returning: $0) }
        }
        let permitted: Bool
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            permitted = true
        case .notDetermined:
            permitted = await withCheckedContinuation { continuation in
                center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
                    continuation.resume(returning: granted)
                }
            }
        default:
            permitted = false
        }
        guard permitted else { return }

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        try? await center.add(request)
    }
}

struct AppEntryView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        if appState.authenticated {
            RootView()
        } else {
            NativeAuthView()
        }
    }
}

struct NativeAuthView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared
    @State private var isRegistering = false
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var loading = false
    @State private var verificationPending = false

    var body: some View {
        ZStack {
            ONEBoardBackground()
            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 24) {
                    HStack(spacing: 14) {
                        LogoView(size: 54)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("ONEBOARD")
                                .font(.title2.weight(.heavy))
                                .tracking(1.3)
                                .foregroundStyle(ONEBoardTheme.ink)
                            Text("Native website operations")
                                .foregroundStyle(ONEBoardTheme.muted)
                        }
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text(isRegistering ? "Create Account" : "Welcome Back")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundStyle(ONEBoardTheme.ink)
                        Text(isRegistering ? "Create your secure ONEBoard workspace." : "Sign in to manage your websites from macOS.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    }

                    VStack(spacing: 12) {
                        if isRegistering {
                            TextField("Name", text: $name)
                        }
                        TextField("Email", text: $email)
                        SecureField("Password", text: $password)
                        if isRegistering {
                            SecureField("Confirm password", text: $confirmPassword)
                        }
                    }
                    .textFieldStyle(.roundedBorder)

                    if !appState.lastAPIError.isEmpty {
                        Label(appState.lastAPIError, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(Color(red: 1, green: 138 / 255, blue: 138 / 255))
                            .font(.caption)
                    }

                    if verificationPending {
                        Label("Verify \(email) using the link we sent, then sign in.", systemImage: "envelope.badge")
                            .foregroundStyle(ONEBoardTheme.success)
                            .font(.caption)
                        Button("Resend Verification Email") {
                            Task { await resendVerification() }
                        }
                        .buttonStyle(.bordered)
                    }

                    Button(loading ? "Please wait..." : isRegistering ? "Create Account" : "Sign In") {
                        Task { await submit() }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .frame(maxWidth: .infinity)
                    .disabled(loading)

                    Button(isRegistering ? "I already have an account" : "Create a new account") {
                        isRegistering.toggle()
                        verificationPending = false
                        appState.lastAPIError = ""
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(ONEBoardTheme.brand)
                    .frame(maxWidth: .infinity)
                }
                .padding(30)
                .frame(maxWidth: 460)
                .oneBoardGlass(cornerRadius: 26, strong: true)
            }
            .padding(.horizontal, 28)
            .padding(.top, 34)
        }
        .tint(ONEBoardTheme.brandDark)
    }

    private func submit() async {
        loading = true
        defer { loading = false }
        do {
            let response: [String: Any]
            if isRegistering {
                response = try await api.register(name: name, email: email, password: password, confirmPassword: confirmPassword)
            } else {
                response = try await api.login(email: email, password: password)
            }
            if response["verification_required"] as? Bool == true {
                verificationPending = true
                isRegistering = false
                appState.lastAPIError = ""
                return
            }
            if let user = response["user"] as? [String: Any] {
                appState.userName = user["name"] as? String ?? ""
                appState.openAIKeySaved = user["openai_api_key_configured"] as? Bool ?? false
            }
            appState.authenticated = true
            appState.apiStatus = "Signed in"
            appState.lastAPIError = ""
        } catch ONEBoardAPIError.verificationRequired(let message) {
            verificationPending = true
            isRegistering = false
            appState.lastAPIError = message
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func resendVerification() async {
        loading = true
        defer { loading = false }
        do {
            _ = try await api.resendVerification(email: email)
            appState.lastAPIError = "A new verification email has been sent."
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }
}

enum AppSection: String, CaseIterable, Identifiable {
    case dashboard = "Dashboard"
    case siteManager = "Site Manager"
    case securityScan = "Security Scan"
    case settings = "Settings"
    case help = "Help"

    var id: String { rawValue }

    var systemImage: String {
        switch self {
        case .dashboard: "chart.bar.xaxis"
        case .siteManager: "folder.badge.gearshape"
        case .securityScan: "shield.lefthalf.filled"
        case .settings: "gearshape"
        case .help: "questionmark.circle"
        }
    }
}

enum RemoteAuthMethod: String, CaseIterable, Identifiable {
    case sshKey = "SSH Key"
    case password = "Password"

    var id: String { rawValue }
}

struct RootView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        NavigationSplitView {
            Sidebar()
                .navigationSplitViewColumnWidth(min: 214, ideal: 246, max: 270)
        } detail: {
            DetailView(section: appState.selectedSection)
        }
        .navigationSplitViewStyle(.balanced)
        .tint(ONEBoardTheme.brandDark)
        .foregroundStyle(ONEBoardTheme.ink)
        .textFieldStyle(.roundedBorder)
        .background(ONEBoardBackground())
        .overlay(alignment: .topTrailing) {
            if let notification = appState.processNotification {
                ProcessNotificationBanner(notification: notification) {
                    appState.dismissProcessNotification()
                }
                .padding(.top, 18)
                .padding(.trailing, 22)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeOut(duration: 0.22), value: appState.processNotification?.id)
    }
}

struct ProcessNotificationBanner: View {
    let notification: ProcessNotification
    let dismiss: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            Image(systemName: notification.kind.systemImage)
                .font(.title3.weight(.semibold))
                .foregroundStyle(notification.kind.color)
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 4) {
                Text(notification.title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(ONEBoardTheme.ink)
                Text(notification.message)
                    .font(.caption)
                    .foregroundStyle(ONEBoardTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button(action: dismiss) {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(ONEBoardTheme.muted)
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss notification")
        }
        .padding(14)
        .frame(width: 390, alignment: .leading)
        .background(ONEBoardTheme.surfaceStrong, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(notification.kind.color.opacity(0.46), lineWidth: 1)
        }
        .shadow(color: Color.black.opacity(0.35), radius: 16, x: 0, y: 8)
        .accessibilityElement(children: .combine)
    }
}

struct Sidebar: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared

    var body: some View {
        VStack(spacing: 0) {
            Color.clear
                .frame(height: 38)

            HStack(spacing: 11) {
                LogoView(size: 43)
                VStack(alignment: .leading, spacing: 2) {
                    Text("ONEBOARD")
                        .font(.system(size: 16, weight: .heavy, design: .rounded))
                        .tracking(1.1)
                        .foregroundStyle(ONEBoardTheme.ink)
                    Text("Website command center")
                        .font(.caption2)
                        .foregroundStyle(ONEBoardTheme.muted)
                }
            }
            .padding(11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [ONEBoardTheme.surfaceHighlight, ONEBoardTheme.surface],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            }
            .padding(.horizontal, 13)

            Text("WORKSPACE")
                .font(.caption2.weight(.semibold))
                .tracking(1.5)
                .foregroundStyle(ONEBoardTheme.faint)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 18)
                .padding(.top, 24)
                .padding(.bottom, 9)

            VStack(spacing: 7) {
                ForEach(AppSection.allCases) { section in
                    Button {
                        withAnimation(.easeOut(duration: 0.18)) {
                            appState.selectedSection = section
                        }
                    } label: {
                        HStack(spacing: 11) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 9, style: .continuous)
                                    .fill(
                                        appState.selectedSection == section
                                            ? ONEBoardTheme.brand.opacity(0.18)
                                            : Color.white.opacity(0.035)
                                    )
                                Image(systemName: section.systemImage)
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(
                                        appState.selectedSection == section
                                            ? ONEBoardTheme.brand
                                            : ONEBoardTheme.muted
                                    )
                            }
                            .frame(width: 34, height: 34)

                            Text(section.rawValue)
                                .font(.system(size: 14, weight: appState.selectedSection == section ? .semibold : .medium))
                                .foregroundStyle(appState.selectedSection == section ? ONEBoardTheme.ink : ONEBoardTheme.muted)

                            Spacer(minLength: 4)

                            if appState.selectedSection == section {
                                Capsule()
                                    .fill(ONEBoardTheme.brand)
                                    .frame(width: 4, height: 18)
                                    .shadow(color: ONEBoardTheme.brand.opacity(0.7), radius: 5)
                            }
                        }
                        .padding(.horizontal, 9)
                        .frame(maxWidth: .infinity, minHeight: 46)
                        .contentShape(Rectangle())
                        .background {
                            RoundedRectangle(cornerRadius: 13, style: .continuous)
                                .fill(
                                    appState.selectedSection == section
                                        ? LinearGradient(
                                            colors: [Color.white.opacity(0.14), ONEBoardTheme.brandDark.opacity(0.22)],
                                            startPoint: .leading,
                                            endPoint: .trailing
                                        )
                                        : LinearGradient(colors: [.clear, .clear], startPoint: .leading, endPoint: .trailing)
                                )
                        }
                        .overlay {
                            RoundedRectangle(cornerRadius: 13, style: .continuous)
                                .stroke(appState.selectedSection == section ? ONEBoardTheme.line : .clear, lineWidth: 1)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)

            Spacer(minLength: 12)

            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 7) {
                    Circle()
                        .fill(appState.lastAPIError.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning)
                        .frame(width: 7, height: 7)
                        .shadow(color: (appState.lastAPIError.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning).opacity(0.65), radius: 5)
                    Text("LOCAL SERVICE")
                        .font(.caption2.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(ONEBoardTheme.faint)
                }
                Text(appState.apiStatus)
                    .font(.caption)
                    .foregroundStyle(ONEBoardTheme.muted)
                    .lineLimit(1)
            }
            .padding(11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(ONEBoardTheme.line.opacity(0.7), lineWidth: 1)
            }
            .padding(.horizontal, 13)
            .padding(.bottom, 10)

            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [ONEBoardTheme.brand, ONEBoardTheme.brandDark],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                    Text(userInitial)
                        .font(.caption.bold())
                        .foregroundStyle(.white)
                }
                .frame(width: 34, height: 34)

                VStack(alignment: .leading, spacing: 2) {
                    Text(appState.userName.isEmpty ? "ONEBoard User" : appState.userName)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(ONEBoardTheme.ink)
                        .lineLimit(1)
                    Text("Native workspace")
                        .font(.caption2)
                        .foregroundStyle(ONEBoardTheme.faint)
                }

                Spacer(minLength: 4)

                Button {
                    Task { await logout() }
                } label: {
                    Image(systemName: "rectangle.portrait.and.arrow.right")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(ONEBoardTheme.muted)
                        .frame(width: 28, height: 28)
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .buttonStyle(.plain)
                .help("Sign out")
            }
            .padding(.horizontal, 14)
            .padding(.top, 11)
            .padding(.bottom, 14)
            .background(Color.black.opacity(0.10))
        }
        .background(
            LinearGradient(
                colors: [ONEBoardTheme.sidebarTop.opacity(0.98), ONEBoardTheme.sidebarBottom.opacity(0.96)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
        .overlay(alignment: .trailing) {
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, ONEBoardTheme.brand.opacity(0.32), .clear],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 1)
        }
    }

    private var userInitial: String {
        String((appState.userName.first ?? "O")).uppercased()
    }

    private func logout() async {
        do {
            _ = try await api.logout()
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
        appState.authenticated = false
        appState.userName = ""
    }
}

struct DetailView: View {
    @EnvironmentObject private var appState: AppState
    let section: AppSection

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Header(title: section.rawValue, subtitle: subtitle)
                    ServiceStatusBar(status: appState.apiStatus, error: appState.lastAPIError)

                    switch section {
                    case .dashboard:
                        DashboardNativeView()
                    case .siteManager:
                        SiteManagerNativeView()
                    case .securityScan:
                        SecurityScanNativeView()
                    case .settings:
                        SettingsNativeView()
                    case .help:
                        HelpNativeView()
                    }
                }
                .frame(maxWidth: 1440, alignment: .leading)
                .padding(.horizontal, proxy.size.width < 760 ? 16 : 24)
                .padding(.top, 42)
                .padding(.bottom, 28)
                .frame(maxWidth: .infinity)
            }
            .scrollIndicators(.hidden)
        }
        .background(ONEBoardBackground())
    }

    private var subtitle: String {
        switch section {
        case .dashboard: "Search performance and operating overview."
        case .siteManager: "AI updates, assets, files, backups, and remote deploy."
        case .securityScan: "Passive domain security checks and scan history."
        case .settings: "Account, company profile, and AI configuration."
        case .help: "Detailed guidance for every ONEBoard tool."
        }
    }
}

struct ServiceStatusBar: View {
    @EnvironmentObject private var service: ONEBoardService
    @EnvironmentObject private var appState: AppState
    let status: String
    let error: String

    var body: some View {
        HStack(spacing: 10) {
            ZStack {
                Circle()
                    .fill((error.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning).opacity(0.18))
                    .frame(width: 22, height: 22)
                Circle()
                    .fill(error.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning)
                    .frame(width: 8, height: 8)
                    .shadow(color: (error.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning).opacity(0.75), radius: 5)
            }
            Text(error.isEmpty ? "ENGINE ONLINE" : "ENGINE NOTICE")
                .font(.caption2.weight(.bold))
                .tracking(0.8)
                .foregroundStyle(error.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning)
            Divider()
                .frame(height: 14)
                .overlay(ONEBoardTheme.line)
            Text(status)
                .font(.caption.weight(.medium))
                .foregroundStyle(ONEBoardTheme.muted)
                .lineLimit(1)
            if !error.isEmpty {
                Divider()
                    .frame(height: 14)
                    .overlay(ONEBoardTheme.line)
                Text(error)
                    .font(.caption)
                    .foregroundStyle(ONEBoardTheme.muted)
                    .lineLimit(1)
            }
            Spacer()
            Button {
                Task {
                    await service.ensureRunning()
                    appState.apiStatus = service.status
                    appState.lastAPIError = service.error
                }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(ONEBoardTheme.brand)
                    .frame(width: 25, height: 25)
                    .background(ONEBoardTheme.brand.opacity(0.10), in: Circle())
            }
            .buttonStyle(.plain)
            .help("Restart or reconnect to the local service")
        }
        .padding(.vertical, 7)
        .padding(.horizontal, 10)
        .oneBoardGlass(cornerRadius: 15, strong: true)
    }
}

struct Header: View {
    let title: String
    let subtitle: String

    var body: some View {
        HStack(alignment: .center, spacing: 15) {
            LogoView(size: 58)
                .shadow(color: ONEBoardTheme.brand.opacity(0.24), radius: 12, x: 0, y: 7)

            VStack(alignment: .leading, spacing: 5) {
                Text("ONEBOARD  /  \(title.uppercased())")
                    .font(.caption2.weight(.bold))
                    .tracking(1.3)
                    .foregroundStyle(ONEBoardTheme.brand)
                Text(title)
                    .font(.system(size: 29, weight: .bold, design: .rounded))
                    .foregroundStyle(ONEBoardTheme.ink)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(ONEBoardTheme.muted)
                    .lineLimit(2)
            }

            Spacer(minLength: 12)

            HStack(spacing: 7) {
                Image(systemName: "apple.logo")
                Text("NATIVE")
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
            }
            .foregroundStyle(ONEBoardTheme.ink)
            .padding(.vertical, 7)
            .padding(.horizontal, 10)
            .background(Color.black.opacity(0.18), in: Capsule())
            .overlay {
                Capsule()
                    .stroke(ONEBoardTheme.line, lineWidth: 1)
            }
        }
        .padding(18)
        .oneBoardGlass(cornerRadius: 22)
    }
}

struct LogoView: View {
    let size: CGFloat

    var body: some View {
        if let image = loadLogoImage() {
            Image(nsImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: size, height: size)
                .clipShape(RoundedRectangle(cornerRadius: max(9, size * 0.22), style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: max(9, size * 0.22), style: .continuous)
                        .stroke(Color.white.opacity(0.32), lineWidth: 1)
                }
        } else {
            RoundedRectangle(cornerRadius: max(9, size * 0.22), style: .continuous)
                .fill(LinearGradient(colors: [ONEBoardTheme.brand, ONEBoardTheme.brandDark], startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: size, height: size)
                .overlay(Text("OB").foregroundStyle(.white).bold())
                .overlay {
                    RoundedRectangle(cornerRadius: max(9, size * 0.22), style: .continuous)
                        .stroke(Color.white.opacity(0.42), lineWidth: 1)
                }
        }
    }

    private func loadLogoImage() -> NSImage? {
        if let image = NSImage(named: "Logo") {
            return image
        }

        if let url = Bundle.main.url(forResource: "Logo", withExtension: "jpeg") {
            return NSImage(contentsOf: url)
        }

        return nil
    }
}

struct NativeCard<Content: View>: View {
    let title: String
    let systemImage: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ONEBoardTheme.brand)
                    .frame(width: 29, height: 29)
                    .background(ONEBoardTheme.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(ONEBoardTheme.brand.opacity(0.16), lineWidth: 1)
                    }
                Text(title)
                    .font(.headline)
                    .foregroundStyle(ONEBoardTheme.ink)
                Spacer(minLength: 0)
            }
            content
        }
        .padding(17)
        .frame(maxWidth: .infinity, alignment: .leading)
        .oneBoardGlass(cornerRadius: 20)
    }
}

struct DashboardNativeView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared
    @State private var selectedProperty = ""
    @State private var searchConsoleSites: [SearchConsoleSite] = []
    @State private var connected = false
    @State private var isLoading = false
    @State private var searchConsoleError = ""
    @State private var isCreatingPage = false
    @State private var pageCreationMessage = ""

    @State private var stats = [
        SearchMetric(label: "Clicks", value: "0", detail: "Search Console"),
        SearchMetric(label: "Impressions", value: "0", detail: "Search Console"),
        SearchMetric(label: "CTR", value: "0%", detail: "Search Console"),
        SearchMetric(label: "Position", value: "-", detail: "Search Console")
    ]

    @State private var keywords: [SearchRow] = []

    @State private var pages: [PageRow] = []

    @State private var opportunities: [SeoOpportunity] = []
    @State private var queryChart: [SearchChartEntry] = []
    @State private var pageChart: [SearchChartEntry] = []

    private var selectedSite: SearchConsoleSite? {
        searchConsoleSites.first { $0.siteURL == selectedProperty }
    }

    private var selectedPropertyLabel: String {
        selectedSite?.displayName ?? (connected ? "Choose a Search Console property" : "Not connected")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            NativeCard(title: "Google Search Console", systemImage: "magnifyingglass") {
                HStack(alignment: .center, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(selectedPropertyLabel)
                            .font(.headline)
                            .foregroundStyle(ONEBoardTheme.ink)
                        Text(connected ? "Live Google data connection. Select a property to review search performance." : "Connect the Google account that has access to your Search Console properties.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    }
                    Spacer()
                    Button(isLoading ? "Loading..." : connected ? "Refresh" : "Connect Google") {
                        Task {
                            if connected {
                                await loadDashboard()
                            } else {
                                await connectGoogle()
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isLoading)
                    if connected {
                        Button("Change Google Account") {
                            Task { await connectGoogle() }
                        }
                        .disabled(isLoading)
                        Button("Disconnect Google", role: .destructive) {
                            Task { await disconnectGoogle() }
                        }
                        .disabled(isLoading)
                    }
                }
            }

            LazyVGrid(columns: compactGridColumns, spacing: 12) {
                ForEach(stats) { metric in
                    MetricTile(metric: metric)
                }
            }

            NativeCard(title: "Property", systemImage: "globe") {
                VStack(alignment: .leading, spacing: 10) {
                    if !searchConsoleError.isEmpty {
                        Label(searchConsoleError, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption)
                            .foregroundStyle(ONEBoardTheme.warning)
                    }

                    if searchConsoleSites.isEmpty {
                        Text(connected ? "This Google account returned no Search Console properties. Use Change Google Account if the properties belong to another account." : "Connect Google to load Search Console properties.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    } else {
                        Picker(
                            "Search Console property",
                            selection: Binding(
                                get: { selectedProperty },
                                set: { newValue in
                                    guard newValue != selectedProperty else { return }
                                    selectedProperty = newValue
                                    Task { await selectProperty(newValue) }
                                }
                            )
                        ) {
                            Text("Select a Search Console property")
                                .tag("")
                            ForEach(searchConsoleSites) { site in
                                Text(site.menuLabel)
                                    .tag(site.siteURL)
                                    .disabled(!site.canReadAnalytics)
                            }
                        }
                        .pickerStyle(.menu)

                        if let selectedSite {
                            Label(selectedSite.permissionLabel, systemImage: selectedSite.canReadAnalytics ? "checkmark.shield.fill" : "exclamationmark.shield.fill")
                                .font(.caption)
                                .foregroundStyle(selectedSite.canReadAnalytics ? ONEBoardTheme.success : ONEBoardTheme.warning)
                        }
                    }
                }
            }

            LazyVGrid(columns: gridColumns, spacing: 16) {
                NativeCard(title: "Click Distribution", systemImage: "chart.bar") {
                    VStack(spacing: 10) {
                        if queryChart.isEmpty {
                            Text("No query data for the selected date range.")
                                .foregroundStyle(ONEBoardTheme.muted)
                        } else {
                            ForEach(queryChart) { entry in
                                BarRow(label: entry.label, value: entry.display, percent: CGFloat(entry.percent))
                            }
                        }
                    }
                }

                NativeCard(title: "Top Pages by Impressions", systemImage: "chart.xyaxis.line") {
                    VStack(spacing: 10) {
                        if pageChart.isEmpty {
                            Text("No page data for the selected date range.")
                                .foregroundStyle(ONEBoardTheme.muted)
                        } else {
                            ForEach(pageChart) { entry in
                                BarRow(label: entry.label, value: entry.display, percent: CGFloat(entry.percent))
                            }
                        }
                    }
                }
            }

            NativeCard(title: "SEO Opportunities", systemImage: "sparkles") {
                VStack(alignment: .leading, spacing: 12) {
                    if !pageCreationMessage.isEmpty {
                        Label(
                            pageCreationMessage,
                            systemImage: pageCreationMessage.hasPrefix("Unable") ? "exclamationmark.triangle.fill" : "checkmark.circle.fill"
                        )
                        .font(.caption)
                        .foregroundStyle(pageCreationMessage.hasPrefix("Unable") ? ONEBoardTheme.warning : ONEBoardTheme.success)
                    }
                    LazyVGrid(columns: gridColumns, spacing: 12) {
                    ForEach(opportunities) { item in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(item.title)
                                .font(.headline)
                                .foregroundStyle(ONEBoardTheme.ink)
                            Text(item.keyword)
                                .foregroundStyle(ONEBoardTheme.muted)
                            HStack {
                                StatPill(label: "Impressions", value: item.impressions)
                                StatPill(label: "Clicks", value: item.clicks)
                                StatPill(label: "Position", value: item.position)
                            }
                            Button(isCreatingPage ? "Creating..." : "Create Page") {
                                Task { await createSEOPage(item) }
                            }
                                .buttonStyle(.borderedProminent)
                                .disabled(isCreatingPage)
                        }
                        .padding(12)
                        .background(Color.black.opacity(0.15))
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(ONEBoardTheme.line)
                        }
                    }
                    }
                }
            }

            LazyVGrid(columns: gridColumns, spacing: 16) {
                SearchTable(title: "Top Keywords", rows: keywords)
                PageTable(title: "Pages with Traffic", rows: pages)
            }
        }
        .task {
            await loadDashboard()
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            Task { await loadDashboard() }
        }
    }

    private func loadDashboard() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.dashboard()
            if let gsc = response["gsc"] as? [String: Any] {
                applySearchConsoleDashboard(gsc)
            }
        } catch {
            appState.apiStatus = "ONEBoard service unavailable"
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func applySearchConsoleDashboard(_ gsc: [String: Any]) {
        connected = gsc["connected"] as? Bool ?? false
        searchConsoleError = gsc["error"] as? String ?? ""

        searchConsoleSites = (gsc["sites"] as? [[String: Any]] ?? []).compactMap { site in
            guard let siteURL = site["siteUrl"] as? String, !siteURL.isEmpty else {
                return nil
            }
            return SearchConsoleSite(
                siteURL: siteURL,
                permissionLevel: site["permissionLevel"] as? String ?? "unknown"
            )
        }

        let serverSelection = gsc["selected_site_url"] as? String ?? ""
        if searchConsoleSites.contains(where: { $0.siteURL == serverSelection }) {
            selectedProperty = serverSelection
        } else {
            selectedProperty = searchConsoleSites.first(where: \.canReadAnalytics)?.siteURL ?? ""
        }

        if let apiStats = gsc["stats"] as? [[String: Any]] {
            stats = apiStats.map {
                SearchMetric(
                    label: $0["label"] as? String ?? "",
                    value: stringify($0["value"]),
                    detail: "Search Console"
                )
            }
        }
        if let apiQueries = gsc["queries"] as? [[String: Any]] {
            keywords = apiQueries.map {
                SearchRow(
                    key: $0["key"] as? String ?? "",
                    clicks: stringify($0["clicks"]),
                    impressions: stringify($0["impressions"]),
                    ctr: stringify($0["ctr"]),
                    position: stringify($0["position"])
                )
            }
        }
        if let apiPages = gsc["pages"] as? [[String: Any]] {
            pages = apiPages.map {
                PageRow(
                    url: $0["key"] as? String ?? "",
                    clicks: stringify($0["clicks"]),
                    impressions: stringify($0["impressions"]),
                    position: stringify($0["position"])
                )
            }
        }
        if let apiOpportunities = gsc["seo_opportunities"] as? [[String: Any]] {
            opportunities = apiOpportunities.map {
                SeoOpportunity(
                    title: $0["title"] as? String ?? "",
                    keyword: $0["keyword"] as? String ?? "",
                    impressions: stringify($0["impressions"]),
                    clicks: stringify($0["clicks"]),
                    position: stringify($0["position"])
                )
            }
        }
        if let apiQueryChart = gsc["query_chart"] as? [[String: Any]] {
            queryChart = apiQueryChart.map {
                SearchChartEntry(
                    label: $0["label"] as? String ?? "",
                    display: stringify($0["display"]),
                    percent: numericInt($0["pct"])
                )
            }
        }
        if let apiPageChart = gsc["page_chart"] as? [[String: Any]] {
            pageChart = apiPageChart.map {
                SearchChartEntry(
                    label: $0["label"] as? String ?? "",
                    display: stringify($0["display"]),
                    percent: numericInt($0["pct"])
                )
            }
        }

        if searchConsoleError.isEmpty {
            appState.apiStatus = connected ? "Search Console connected" : "Connected to ONEBoard service"
            appState.lastAPIError = ""
        } else {
            appState.apiStatus = "Search Console needs attention"
            appState.lastAPIError = searchConsoleError
        }
    }

    private func selectProperty(_ siteURL: String) async {
        guard !isLoading,
              let site = searchConsoleSites.first(where: { $0.siteURL == siteURL }),
              site.canReadAnalytics else {
            return
        }

        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.selectSearchConsoleSite(siteURL)
            if let gsc = response["gsc"] as? [String: Any] {
                applySearchConsoleDashboard(gsc)
            }
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func connectGoogle() async {
        do {
            let url = try await api.createSearchConsoleConnection()
            _ = await MainActor.run {
                NSWorkspace.shared.open(url)
            }
            appState.apiStatus = "Google authorization opened"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func disconnectGoogle() async {
        do {
            let response = try await api.disconnectSearchConsole()
            if let gsc = response["gsc"] as? [String: Any] {
                applySearchConsoleDashboard(gsc)
            }
            appState.apiStatus = "Google Search Console disconnected"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func createSEOPage(_ opportunity: SeoOpportunity) async {
        isCreatingPage = true
        pageCreationMessage = ""
        defer { isCreatingPage = false }
        do {
            let response = try await api.createSearchConsolePage(
                title: opportunity.title,
                keyword: opportunity.keyword,
                expectedDirectory: appState.connectedDirectory
            )
            if let manager = response["manager"] as? [String: Any],
               let directory = manager["directory"] as? [String: Any] {
                appState.connectedDirectory = stringify(directory["path"])
            }
            let notification = response["notification"] as? String
                ?? "SEO page \"\(opportunity.title)\" for keyword \"\(opportunity.keyword)\" was created from SEO Opportunities. Review it in Site Manager before publishing."
            pageCreationMessage = notification
            appState.apiStatus = notification
            appState.lastAPIError = ""
            appState.notifyProcess(
                title: "SEO Opportunities · Page created",
                message: "\"\(opportunity.title)\" is ready for review in Site Manager."
            )
        } catch {
            pageCreationMessage = "Unable to create the SEO page: \(error.localizedDescription)"
            appState.lastAPIError = pageCreationMessage
            appState.notifyProcess(
                title: "SEO Opportunities · Page creation failed",
                message: error.localizedDescription,
                kind: .failure
            )
        }
    }
}

private func stringify(_ value: Any?) -> String {
    if let value = value as? String {
        return value
    }
    if let value = value as? Int {
        return "\(value)"
    }
    if let value = value as? Double {
        return String(format: "%.1f", value)
    }
    return ""
}

private func numericInt(_ value: Any?) -> Int {
    if let value = value as? Int {
        return value
    }
    if let value = value as? Double {
        return Int(value)
    }
    if let value = value as? NSNumber {
        return value.intValue
    }
    if let value = value as? String {
        return Int(value) ?? 0
    }
    return 0
}

struct SiteManagerNativeView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared
    @State private var prompt = ""
    @State private var remotePath = ""
    @State private var remoteUser = ""
    @State private var remotePort = "22"
    @State private var selectedImageName = "No image selected"
    @State private var seoTitle = ""
    @State private var seoKeyword = ""
    @State private var seoTone = "Professional"
    @State private var seoAudience = "Website visitors"
    @State private var seoCTA = "Contact us"
    @State private var terminalCommand = ""
    @State private var terminalOutput = "Ready for restricted website commands."
    @State private var remotePassword = ""
    @State private var sshKeyPath = ""
    @State private var selectedImageURL: URL?
    @State private var selectedAssetPath = ""
    @State private var backups: [SiteBackup] = []
    @State private var updates: [SiteUpdate] = []
    @State private var files: [SiteFileEntry] = []
    @State private var assets: [SiteAsset] = []
    @State private var currentPath = ""
    @State private var parentPath = ""
    @State private var remoteConnected = false
    @State private var remoteMatchesDirectory = false
    @State private var remoteHasSavedPassword = false
    @State private var remoteTestInProgress = false
    @State private var remoteTestSucceeded = false
    @State private var remoteTestMessage = "Enter the server details, then test the connection."
    @State private var testedRemoteDraftFingerprint = ""
    @State private var savedRemoteDraftIdentity = ""
    @State private var sshKey = SiteSSHKey()
    @State private var managerRequestGeneration = 0
    @State private var managerMessage = ""
    @State private var pendingAction: SiteManagerDestructiveAction?
    @State private var waitingForManagerUnlock = false
    @State private var selectedAIProvider = "openai"
    @State private var selectedAIModel = ""
    @State private var siteAIProviderModels: [String: [String]] = [
        "openai": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-5-mini", "gpt-5"],
        "anthropic": ["claude-sonnet-4", "claude-3-5-haiku"],
        "openrouter": ["openai/gpt-5", "anthropic/claude-sonnet-4", "google/gemini-2.5-pro"],
        "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
    ]
    @State private var aiChatMessages: [SiteChatMessage] = []
    @State private var aiStatusNote = ""
    @State private var proposedPlan = ""
    @State private var proposedPlanPrompt = ""
    @State private var localChatSeed = -1

    private var latestPublishableUpdate: SiteUpdate? {
        updates.first { $0.status == "approved" }
    }

    private var isBusy: Bool {
        isLoading || isConnectingDirectory
    }

    private var isLoading: Bool {
        appState.siteManagerOperationInProgress
    }

    private var isConnectingDirectory: Bool {
        appState.siteManagerDirectoryTransition
    }

    private var remoteDraftIdentity: String {
        [
            appState.remoteHost.trimmingCharacters(in: .whitespacesAndNewlines),
            remotePort.trimmingCharacters(in: .whitespacesAndNewlines),
            remoteUser.trimmingCharacters(in: .whitespacesAndNewlines),
            remotePath.trimmingCharacters(in: .whitespacesAndNewlines),
            sshKeyPath.trimmingCharacters(in: .whitespacesAndNewlines),
            appState.remoteAuthMethod == .password ? "password" : "key"
        ].joined(separator: "|")
    }

    private var remoteDestinationLabel: String {
        let host = appState.remoteHost.trimmingCharacters(in: .whitespacesAndNewlines)
        let username = remoteUser.trimmingCharacters(in: .whitespacesAndNewlines)
        let path = remotePath.trimmingCharacters(in: .whitespacesAndNewlines)
        return "\(username)@\(host):\(path)"
    }

    private var remoteDraftFingerprint: String {
        [
            remoteDraftIdentity,
            String(remotePassword.hashValue),
            appState.connectedDirectory
        ].joined(separator: "|")
    }

    private var remoteDraftIsComplete: Bool {
        let port = Int(remotePort.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
        let requiredFieldsPresent = !appState.remoteHost.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !remoteUser.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !remotePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (1...65_535).contains(port)
        guard requiredFieldsPresent else { return false }
        if appState.remoteAuthMethod == .password {
            return remoteHasSavedPassword || !remotePassword.isEmpty
        }
        return true
    }

    private var remoteDraftMatchesSavedConnection: Bool {
        remoteConnected && !savedRemoteDraftIdentity.isEmpty && savedRemoteDraftIdentity == remoteDraftIdentity
    }

    private var currentRemoteDraftWasTested: Bool {
        remoteTestSucceeded
            && !testedRemoteDraftFingerprint.isEmpty
            && testedRemoteDraftFingerprint == remoteDraftFingerprint
    }

    private var remoteWorkflowTitle: String {
        if remoteTestInProgress { return "Testing SSH connection..." }
        if remoteConnected && remoteMatchesDirectory && remoteDraftMatchesSavedConnection {
            return "Remote website linked and ready to publish"
        }
        if currentRemoteDraftWasTested { return "Connection verified" }
        if remoteConnected && remoteDraftMatchesSavedConnection { return "Connection saved — download the website next" }
        if remoteConnected { return "Settings changed — test this draft" }
        return "Remote connection not tested"
    }

    private var remoteWorkflowMessage: String {
        if remoteConnected && remoteMatchesDirectory && remoteDraftMatchesSavedConnection {
            return "ONEBoard edits the downloaded local workspace. After reviewing and approving an update, Publish sends that local version back to the server over SSH."
        }
        return remoteTestMessage
    }

    private var remoteWorkflowColor: Color {
        if remoteTestInProgress { return ONEBoardTheme.brand }
        if (remoteConnected && remoteMatchesDirectory && remoteDraftMatchesSavedConnection) || currentRemoteDraftWasTested {
            return ONEBoardTheme.success
        }
        if remoteConnected || remoteTestMessage != "Enter the server details, then test the connection." {
            return ONEBoardTheme.warning
        }
        return ONEBoardTheme.muted
    }

    private var remoteWorkflowIcon: String {
        if remoteTestInProgress { return "arrow.triangle.2.circlepath" }
        if (remoteConnected && remoteMatchesDirectory && remoteDraftMatchesSavedConnection) || currentRemoteDraftWasTested {
            return "checkmark.circle.fill"
        }
        if remoteConnected { return "exclamationmark.triangle.fill" }
        return "network"
    }

    private var remoteDownloadButtonTitle: String {
        appState.connectedDirectory.isEmpty ? "Connect & Download Remote Website" : "Download Remote Website to Local Workspace"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            LazyVGrid(columns: compactGridColumns, spacing: 12) {
                StatusTile(label: "Directory", value: appState.connectedDirectory.isEmpty ? "Not connected" : "Connected", detail: appState.connectedDirectory.isEmpty ? "Choose website folder" : appState.connectedDirectory)
                StatusTile(label: "Backups", value: "\(backups.count)", detail: backups.first?.filename ?? "No snapshots yet")
                StatusTile(
                    label: "Remote",
                    value: remoteConnected && remoteMatchesDirectory && remoteDraftMatchesSavedConnection
                        ? "Ready"
                        : (currentRemoteDraftWasTested ? "Tested" : (remoteConnected ? "Saved" : "Not connected")),
                    detail: remoteWorkflowTitle
                )
                StatusTile(label: "Updates", value: "\(updates.count)", detail: "Pending review and publish")
            }

            if !managerMessage.isEmpty || !appState.lastAPIError.isEmpty {
                Label(
                    appState.lastAPIError.isEmpty ? managerMessage : appState.lastAPIError,
                    systemImage: appState.lastAPIError.isEmpty ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
                )
                .font(.caption)
                .foregroundStyle(appState.lastAPIError.isEmpty ? ONEBoardTheme.success : ONEBoardTheme.warning)
            }

            NativeCard(title: "Website Directory", systemImage: "folder.badge.gearshape") {
                if appState.connectedDirectory.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Connect a website folder to unlock Site Manager", systemImage: "folder.badge.plus")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(ONEBoardTheme.ink)
                        Text("Google Search Console does not select a local folder automatically. Choose the root folder that contains your website files.")
                            .foregroundStyle(ONEBoardTheme.muted)
                        HStack(spacing: 10) {
                            Button {
                                chooseDirectory()
                            } label: {
                                Label("Select Website Folder...", systemImage: "folder")
                            }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.large)
                            .disabled(isBusy)

                            if isBusy {
                                ProgressView()
                                    .controlSize(.small)
                                Text(isConnectingDirectory ? "Connecting folder..." : "Loading Site Manager...")
                                    .font(.caption)
                                    .foregroundStyle(ONEBoardTheme.muted)
                            }
                        }
                    }
                } else {
                    HStack(spacing: 10) {
                        Text(appState.connectedDirectory)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(ONEBoardTheme.ink)
                            .lineLimit(2)
                        Spacer()
                        Button("Change Folder...") { chooseDirectory() }
                            .disabled(isBusy)
                        Button("Refresh") { Task { await loadSiteManager(path: currentPath) } }
                            .disabled(isBusy)
                        Button("Create Backup") { Task { await createBackup() } }
                            .buttonStyle(.borderedProminent)
                            .disabled(isBusy)
                    }
                }
            }

            NativeCard(title: "AI Website Studio", systemImage: "sparkles") {
                VStack(alignment: .leading, spacing: 12) {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Label("Conversation", systemImage: "message.and.waveform")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(ONEBoardTheme.ink)
                            Spacer()
                            Text("\(siteProviderLabel(selectedAIProvider)) · \(selectedAIModel)")
                                .font(.caption)
                                .foregroundStyle(ONEBoardTheme.muted)
                        }

                        ScrollView {
                            VStack(alignment: .leading, spacing: 8) {
                                if aiChatMessages.isEmpty {
                                    Text("No conversation yet. Send a request to start the assistant workflow.")
                                        .foregroundStyle(ONEBoardTheme.muted)
                                        .padding(.vertical, 8)
                                } else {
                                    ForEach(Array(aiChatMessages.suffix(20))) { message in
                                        HStack {
                                            if message.role == "assistant" {
                                                messageBubble(message, isAssistant: true)
                                                Spacer(minLength: 22)
                                            } else {
                                                Spacer(minLength: 22)
                                                messageBubble(message, isAssistant: false)
                                            }
                                        }
                                    }
                                }

                                if !aiStatusNote.isEmpty {
                                    HStack {
                                        typingBubble(text: aiStatusNote)
                                        Spacer(minLength: 22)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(minHeight: 170, maxHeight: 330)
                        .padding(10)
                        .background(Color.black.opacity(0.20), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(ONEBoardTheme.line, lineWidth: 1)
                        }
                    }

                    HStack {
                        Button("Update Hero") { prompt = QuickPrompt.hero.rawValue }
                        Button("Add Section") { prompt = QuickPrompt.section.rawValue }
                        Button("Improve CTA") { prompt = QuickPrompt.cta.rawValue }
                        Button("Create Landing") { prompt = QuickPrompt.landing.rawValue }
                        Spacer()
                    }

                    HStack(spacing: 12) {
                        Picker("Provider", selection: $selectedAIProvider) {
                            ForEach(siteAIProviderModels.keys.sorted(), id: \.self) { provider in
                                Text(siteProviderLabel(provider)).tag(provider)
                            }
                        }
                        .pickerStyle(.menu)

                        Picker("Model", selection: $selectedAIModel) {
                            ForEach(siteModelsForSelectedProvider, id: \.self) { model in
                                Text(model).tag(model)
                            }
                        }
                        .pickerStyle(.menu)
                    }

                    TextEditor(text: $prompt)
                        .frame(minHeight: 95)
                        .scrollContentBackground(.hidden)
                        .padding(6)
                        .background(Color.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(ONEBoardTheme.line, lineWidth: 1)
                        }
                    HStack {
                        Text(selectedImageName)
                            .foregroundStyle(ONEBoardTheme.muted)
                        Button("Choose Suggested Image...") { chooseImage() }
                            .disabled(appState.connectedDirectory.isEmpty || isBusy)
                        Spacer()
                        Button("Generate Plan") {
                            Task { await generateAIPlan() }
                        }
                        .buttonStyle(.bordered)
                        .disabled(appState.connectedDirectory.isEmpty || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selectedAIModel.isEmpty || isBusy)

                        Button("Send to AI") {
                            pendingAction = .applyAIUpdate
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(appState.connectedDirectory.isEmpty || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selectedAIModel.isEmpty || isBusy)
                    }

                    if !proposedPlan.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Label("Proposed Execution Plan", systemImage: "list.bullet.clipboard")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(ONEBoardTheme.ink)
                                Spacer()
                                Button("Apply Plan") {
                                    pendingAction = .applyAIUpdate
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(isBusy)
                                Button("Clear") {
                                    proposedPlan = ""
                                    proposedPlanPrompt = ""
                                }
                                .disabled(isBusy)
                            }

                            ScrollView {
                                Text(proposedPlan)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .foregroundStyle(ONEBoardTheme.muted)
                                    .textSelection(.enabled)
                            }
                            .frame(minHeight: 90, maxHeight: 210)
                            .padding(10)
                            .background(Color.black.opacity(0.18), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(ONEBoardTheme.line, lineWidth: 1)
                            }
                        }
                    }
                }
            }

            LazyVGrid(columns: gridColumns, spacing: 16) {
                NativeCard(title: "Remote SSH", systemImage: "server.rack") {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: remoteWorkflowIcon)
                                .font(.title3)
                                .foregroundStyle(remoteWorkflowColor)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(remoteWorkflowTitle)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(ONEBoardTheme.ink)
                                Text(remoteWorkflowMessage)
                                    .font(.caption)
                                    .foregroundStyle(ONEBoardTheme.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(10)
                        .background(remoteWorkflowColor.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(remoteWorkflowColor.opacity(0.28), lineWidth: 1)
                                .allowsHitTesting(false)
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            TextField("Server host or IP", text: $appState.remoteHost)
                            HStack {
                                TextField("Port", text: $remotePort)
                                    .frame(maxWidth: 100)
                                TextField("SSH username", text: $remoteUser)
                            }
                            TextField("Remote website path, e.g. /var/www/example.com", text: $remotePath)
                            Picker("Authentication", selection: $appState.remoteAuthMethod) {
                                ForEach(RemoteAuthMethod.allCases) { method in
                                    Text(method.rawValue).tag(method)
                                }
                            }
                            .pickerStyle(.segmented)

                            if appState.remoteAuthMethod == .password {
                                SecureField(
                                    remoteHasSavedPassword ? "Password saved — leave blank to reuse it" : "SSH password",
                                    text: $remotePassword
                                )
                            } else {
                                TextField("SSH private key path", text: $sshKeyPath)
                                HStack {
                                    Button(sshKey.exists ? "ONEBoard SSH Key Ready" : "Generate ONEBoard SSH Key") {
                                        Task { await generateSSHKey() }
                                    }
                                    .disabled(sshKey.exists || isBusy)
                                    if sshKey.exists {
                                        Button("Copy Public Key") { copyToClipboard(sshKey.publicKey) }
                                    }
                                }
                                if sshKey.exists {
                                    Text("Install the copied public key in ~/.ssh/authorized_keys on the remote server, then test the connection.")
                                        .font(.caption)
                                        .foregroundStyle(ONEBoardTheme.muted)
                                }
                            }
                        }
                        .disabled(isBusy)

                        HStack(spacing: 8) {
                            Button {
                                Task { await testRemoteConnection() }
                            } label: {
                                Label(remoteTestInProgress ? "Testing..." : "Test Connection", systemImage: "checkmark.shield")
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!remoteDraftIsComplete || isBusy)

                            Button("Save Settings") {
                                Task { await saveRemoteConnection() }
                            }
                            .disabled(!remoteDraftIsComplete || isBusy)
                        }

                        Button {
                            pendingAction = .syncRemote
                        } label: {
                            Label(remoteDownloadButtonTitle, systemImage: "square.and.arrow.down")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .disabled(!currentRemoteDraftWasTested || isBusy)

                        if latestPublishableUpdate != nil {
                            Button {
                                if let latestPublishableUpdate {
                                    pendingAction = .publishUpdate(latestPublishableUpdate)
                                }
                            } label: {
                                Label("Publish Latest Approved Update", systemImage: "arrow.up.circle")
                            }
                            .disabled(
                                !remoteConnected
                                    || !remoteMatchesDirectory
                                    || !remoteDraftMatchesSavedConnection
                                    || isBusy
                            )
                        }

                        Divider()
                            .overlay(ONEBoardTheme.line)

                        VStack(alignment: .leading, spacing: 6) {
                            Label("How remote editing works", systemImage: "point.3.connected.trianglepath.dotted")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(ONEBoardTheme.ink)
                            Text("1. Test the SSH credentials without saving or changing the website.")
                            Text("2. Connect & Download saves the tested settings and creates or refreshes ONEBoard's managed local workspace.")
                            Text("3. AI Studio, files, backups, and the terminal edit that local workspace only.")
                            Text("4. Review and approve an update, then Publish sends the local website back over SSH.")
                        }
                        .font(.caption)
                        .foregroundStyle(ONEBoardTheme.muted)
                    }
                }

                NativeCard(title: "Update History", systemImage: "clock.arrow.circlepath") {
                    VStack(alignment: .leading, spacing: 12) {
                        if updates.isEmpty {
                            Text("No website updates have been recorded yet.")
                                .foregroundStyle(ONEBoardTheme.muted)
                        } else {
                            ForEach(updates) { update in
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text("\(update.source) · \(update.status.capitalized)")
                                            .font(.headline)
                                        Spacer()
                                        Button("Approve") {
                                            Task { await performUpdateAction(update, action: "approve") }
                                        }
                                        .disabled(update.status != "pending" || isBusy)
                                        Button("Publish") {
                                            pendingAction = .publishUpdate(update)
                                        }
                                        .disabled(
                                            !remoteConnected
                                                || !remoteMatchesDirectory
                                                || !remoteDraftMatchesSavedConnection
                                                || update.status != "approved"
                                                || isBusy
                                        )
                                        Button("Restore") {
                                            pendingAction = .restoreUpdate(update)
                                        }
                                        .disabled(!update.hasSnapshot || isBusy)
                                    }
                                    Text(update.summary)
                                        .foregroundStyle(ONEBoardTheme.muted)
                                    if !update.files.isEmpty {
                                        Text(update.files.prefix(5).map(\.label).joined(separator: "  "))
                                            .font(.caption.monospaced())
                                    }
                                    if !update.diffSummary.isEmpty {
                                        DisclosureGroup("Review Diff") {
                                            ScrollView(.horizontal) {
                                                Text(update.diffSummary)
                                                    .font(.caption.monospaced())
                                                    .textSelection(.enabled)
                                            }
                                        }
                                    }
                                }
                                Divider()
                                    .overlay(ONEBoardTheme.line)
                            }
                        }
                    }
                }

                NativeCard(title: "Asset Library", systemImage: "photo.on.rectangle") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(selectedAssetPath.isEmpty ? selectedImageName : "Selected: \(selectedAssetPath)")
                            .foregroundStyle(ONEBoardTheme.muted)
                        Button("Upload Asset...") { chooseImage() }
                            .disabled(appState.connectedDirectory.isEmpty || isBusy)
                        if assets.isEmpty {
                            Text("No uploaded assets yet.")
                                .font(.caption)
                                .foregroundStyle(ONEBoardTheme.muted)
                        } else {
                            ForEach(assets) { asset in
                                HStack {
                                    Image(systemName: "photo")
                                    Text(asset.name)
                                        .lineLimit(1)
                                    Spacer()
                                    Text(asset.sizeLabel)
                                        .foregroundStyle(ONEBoardTheme.muted)
                                    Button(selectedAssetPath == asset.path ? "Selected" : "Use") {
                                        selectedAssetPath = asset.path
                                        selectedImageName = asset.name
                                    }
                                    .disabled(selectedAssetPath == asset.path)
                                }
                            }
                        }
                    }
                }

                NativeCard(title: "SEO Writer", systemImage: "text.badge.star") {
                    VStack(alignment: .leading, spacing: 10) {
                        TextField("Title", text: $seoTitle)
                        TextField("Target keyword", text: $seoKeyword)
                        TextField("Tone", text: $seoTone)
                        TextField("Audience", text: $seoAudience)
                        TextField("CTA", text: $seoCTA)
                        Button("Create Content") {
                            Task { await createSEOContent() }
                        }
                            .buttonStyle(.borderedProminent)
                            .disabled(appState.connectedDirectory.isEmpty || seoTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || seoKeyword.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isBusy)
                    }
                }
            }

            NativeCard(title: "Backups", systemImage: "clock.arrow.circlepath") {
                VStack(alignment: .leading, spacing: 10) {
                    if backups.isEmpty {
                        Text("No backups yet. Create one before making major changes.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    } else {
                        ForEach(backups) { backup in
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(backup.filename)
                                        .font(.body.monospaced())
                                    Text("\(backup.createdAt) · \(backup.sizeLabel) · \(backup.fileCount) files")
                                        .font(.caption)
                                        .foregroundStyle(ONEBoardTheme.muted)
                                }
                                Spacer()
                                Button("Restore") {
                                    pendingAction = .restoreBackup(backup)
                                }
                                .disabled(!backup.exists || isBusy)
                            }
                            Divider().overlay(ONEBoardTheme.line)
                        }
                    }
                }
            }

            NativeCard(title: "File Explorer", systemImage: "doc.text.magnifyingglass") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button("Up") { Task { await loadSiteManager(path: parentPath) } }
                            .disabled(currentPath.isEmpty || isBusy)
                        Text("/\(currentPath)")
                            .font(.caption.monospaced())
                            .foregroundStyle(ONEBoardTheme.muted)
                        Spacer()
                        Button("Reveal in Finder") { revealCurrentDirectory() }
                            .disabled(appState.connectedDirectory.isEmpty || isBusy)
                    }

                    if files.isEmpty {
                        Text(appState.connectedDirectory.isEmpty ? "Choose a website directory to browse files." : "This folder is empty.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    } else {
                        ForEach(files) { file in
                            HStack {
                                Image(systemName: file.isDirectory ? "folder.fill" : file.isImage ? "photo" : "doc.text")
                                if file.isDirectory {
                                    Button(file.name) {
                                        Task { await loadSiteManager(path: file.path) }
                                    }
                                    .buttonStyle(.plain)
                                    .font(.system(.body, design: .monospaced))
                                    .disabled(isBusy)
                                } else {
                                    Text(file.name)
                                        .font(.system(.body, design: .monospaced))
                                }
                                Spacer()
                                Text(file.modifiedAt)
                                    .font(.caption)
                                    .foregroundStyle(ONEBoardTheme.muted)
                                Text(file.sizeLabel)
                                    .foregroundStyle(ONEBoardTheme.muted)
                                if !file.isDirectory {
                                    Button("Open") { openFile(file) }
                                        .disabled(isBusy)
                                    if file.isImage {
                                        Button("Use Image") {
                                            selectedAssetPath = file.path
                                            selectedImageName = file.name
                                        }
                                        .disabled(isBusy)
                                    }
                                    Button("Delete", role: .destructive) {
                                        pendingAction = .deleteFile(file)
                                    }
                                    .disabled(isBusy)
                                }
                            }
                            Divider()
                                .overlay(ONEBoardTheme.line)
                        }
                    }
                }
            }

            NativeCard(title: "Terminal", systemImage: "terminal") {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Workspace: \(appState.connectedDirectory.isEmpty ? "No directory connected" : appState.connectedDirectory)")
                        .font(.caption)
                        .foregroundStyle(ONEBoardTheme.muted)
                    TextEditor(text: $terminalOutput)
                        .font(.system(.body, design: .monospaced))
                        .frame(minHeight: 90)
                        .scrollContentBackground(.hidden)
                        .padding(6)
                        .background(Color.black.opacity(0.28), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay {
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .stroke(ONEBoardTheme.line, lineWidth: 1)
                        }
                    HStack {
                        TextField("Command", text: $terminalCommand)
                        Button("Run") {
                            Task { await runTerminalCommand() }
                        }
                        .disabled(appState.connectedDirectory.isEmpty || terminalCommand.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isBusy)
                    }
                }
            }
        }
        .task { await loadSiteManagerWhenAvailable() }
        .task { await loadSiteAIProviders() }
        .onChange(of: appState.siteManagerDirectoryTransition) { _, _ in
            refreshAfterManagerUnlockIfNeeded()
        }
        .onChange(of: appState.siteManagerOperationInProgress) { _, _ in
            refreshAfterManagerUnlockIfNeeded()
        }
        .onChange(of: remoteDraftFingerprint) { _, newValue in
            guard !remoteTestInProgress, newValue != testedRemoteDraftFingerprint else { return }
            remoteTestSucceeded = false
            testedRemoteDraftFingerprint = ""
            remoteTestMessage = remoteConnected
                ? "Connection settings changed. Test the connection again."
                : "Enter the server details, then test the connection."
        }
        .onChange(of: selectedAIProvider) { _, newProvider in
            let models = siteAIProviderModels[newProvider] ?? []
            if !models.contains(selectedAIModel) {
                selectedAIModel = models.first ?? ""
            }
        }
        .alert(item: $pendingAction) { action in
            confirmationAlert(for: action)
        }
    }

    private var siteModelsForSelectedProvider: [String] {
        siteAIProviderModels[selectedAIProvider] ?? []
    }

    private func siteProviderLabel(_ provider: String) -> String {
        switch provider {
        case "openai":
            return "OpenAI"
        case "anthropic":
            return "Anthropic"
        case "openrouter":
            return "OpenRouter"
        case "google":
            return "Google"
        default:
            return provider.capitalized
        }
    }

    private func chooseDirectory() {
        guard !isBusy else {
            managerMessage = "Please wait for the current Site Manager operation to finish."
            return
        }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Connect Website"
        panel.message = "Choose the root folder that contains the website you want ONEBoard to manage."

        NSApp.activate(ignoringOtherApps: true)
        guard let window = NSApp.keyWindow ?? NSApp.mainWindow ?? NSApp.windows.first(where: { $0.isVisible }) else {
            managerMessage = ""
            appState.lastAPIError = "ONEBoard could not attach the folder selector to its window. Close duplicate ONEBoard windows and try again."
            appState.apiStatus = "Site Manager needs attention"
            return
        }

        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { return }
            Task { @MainActor in
                await connectDirectory(url.path)
            }
        }
    }

    private func connectDirectory(_ path: String) async {
        guard !isBusy else {
            managerMessage = "Please wait for the current Site Manager operation to finish."
            return
        }
        appState.siteManagerDirectoryTransition = true
        managerRequestGeneration += 1
        let requestGeneration = managerRequestGeneration
        defer { appState.siteManagerDirectoryTransition = false }
        do {
            let response = try await api.connectSiteDirectory(path)
            guard requestGeneration == managerRequestGeneration else { return }
            applySiteManagerResponse(response)
            setOperationSuccess("Website directory connected")
        } catch {
            setOperationError(error)
            await refreshManagerStateAfterFailure()
        }
    }

    private func chooseImage() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .gif, .webP]
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK {
            selectedImageURL = panel.url
            selectedImageName = panel.url?.lastPathComponent ?? "Selected image"
            Task { await uploadSelectedImage() }
        }
    }

    private func uploadSelectedImage() async {
        guard !isBusy, let selectedImageURL else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.uploadAsset(
                fileURL: selectedImageURL,
                expectedDirectory: appState.connectedDirectory
            )
            selectedAssetPath = response["asset_path"] as? String ?? selectedAssetPath
            applySiteManagerResponse(response)
            setOperationSuccess("Asset uploaded")
        } catch {
            setOperationError(error)
        }
    }

    private func runAIUpdate() async {
        await runAIUpdate(promptOverride: nil)
    }

    private func runAIUpdate(promptOverride: String?) async {
        guard !isBusy else { return }
        let candidatePrompt = (promptOverride ?? prompt).trimmingCharacters(in: .whitespacesAndNewlines)
        let submittedPrompt = candidatePrompt.isEmpty ? proposedPlanPrompt.trimmingCharacters(in: .whitespacesAndNewlines) : candidatePrompt
        guard !submittedPrompt.isEmpty else { return }
        appendLocalChat(role: "user", content: submittedPrompt)
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        aiStatusNote = "The AI assistant is reviewing your request and preparing website changes..."
        do {
            let response = try await api.runCodexUpdate(
                prompt: submittedPrompt,
                selectedAsset: selectedAssetPath,
                provider: selectedAIProvider,
                model: selectedAIModel,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            applyTerminalResponse(response)
            prompt = ""
            proposedPlan = ""
            proposedPlanPrompt = ""
            aiStatusNote = ""
            setOperationSuccess("AI update completed (\(siteProviderLabel(selectedAIProvider)) · \(selectedAIModel)) and saved for review")
            let summary = updates.first?.summary ?? "Your website update is ready for review in Update History."
            appState.notifyProcess(title: "Site Manager · AI update completed", message: summary)
        } catch {
            aiStatusNote = ""
            setOperationError(error)
            appState.notifyProcess(title: "Site Manager · AI update failed", message: error.localizedDescription, kind: .failure)
            await refreshManagerStateAfterFailure()
        }
    }

    private func generateAIPlan() async {
        guard !isBusy else { return }
        let submittedPrompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !submittedPrompt.isEmpty else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        aiStatusNote = "The AI assistant is preparing a step-by-step plan before applying changes..."

        do {
            let response = try await api.runAI(
                taskType: "assistant",
                provider: selectedAIProvider,
                model: selectedAIModel,
                prompt: buildExecutionPlanPrompt(userPrompt: submittedPrompt),
                context: appState.connectedDirectory.isEmpty ? "" : "Connected website directory: \(appState.connectedDirectory)"
            )

            let planText = ((response["run"] as? [String: Any])?["response_text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !planText.isEmpty else {
                throw ONEBoardAPIError.server("The model did not return a usable plan.")
            }

            proposedPlan = planText
            proposedPlanPrompt = submittedPrompt
            aiStatusNote = ""
            appendLocalChat(role: "user", content: submittedPrompt)
            appendLocalChat(role: "assistant", content: planText)
            setOperationSuccess("Plan ready. Review it and click Apply Plan when you are ready.")
            appState.notifyProcess(title: "Site Manager · AI plan ready", message: "Review the proposed procedure before applying website changes.")
        } catch {
            aiStatusNote = ""
            setOperationError(error)
            appState.notifyProcess(title: "Site Manager · AI plan failed", message: error.localizedDescription, kind: .failure)
        }
    }

    private func buildExecutionPlanPrompt(userPrompt: String) -> String {
        var parts: [String] = []
        parts.append("Create a concise implementation plan for this website update request.")
        parts.append("Explain: 1) what files/components are likely to change, 2) why, 3) risk checks before publish, and 4) expected visible outcome.")
        parts.append("Do not apply changes. This is plan-only guidance for user confirmation.")
        if !selectedAssetPath.isEmpty {
            parts.append("User selected image asset: \(selectedAssetPath)")
        }
        parts.append("User request: \(userPrompt)")
        return parts.joined(separator: "\n\n")
    }

    private func loadSiteAIProviders() async {
        do {
            let response = try await api.aiProviders()
            if let providers = response["providers"] as? [[String: Any]] {
                var discovered: [String: [String]] = [:]
                for provider in providers {
                    guard let key = provider["key"] as? String else { continue }
                    guard (provider["supports_site_updates"] as? Bool ?? false) else { continue }
                    discovered[key] = provider["models"] as? [String] ?? []
                }
                if !discovered.isEmpty {
                    siteAIProviderModels = discovered
                }
            }

            if let policy = response["policy"] as? [String: Any] {
                let provider = (policy["provider"] as? String ?? "openai").lowercased()
                if siteAIProviderModels[provider] != nil {
                    selectedAIProvider = provider
                }
                let model = policy["model"] as? String ?? ""
                if (siteAIProviderModels[selectedAIProvider] ?? []).contains(model) {
                    selectedAIModel = model
                }
            }

            if selectedAIModel.isEmpty {
                selectedAIModel = siteAIProviderModels[selectedAIProvider]?.first ?? ""
            }
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func createSEOContent() async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.createSEOContent(
                title: seoTitle,
                keyword: seoKeyword,
                tone: seoTone,
                audience: seoAudience,
                cta: seoCTA,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            applyTerminalResponse(response)
            let notification = response["notification"] as? String
                ?? "SEO page \"\(seoTitle)\" for keyword \"\(seoKeyword)\" was created in Site Manager. Review it before publishing."
            setOperationSuccess(notification)
            appState.notifyProcess(
                title: "Site Manager · SEO Writer · Page created",
                message: "\"\(seoTitle)\" is ready for review before publishing."
            )
        } catch {
            setOperationError(error)
            appState.notifyProcess(
                title: "Site Manager · SEO Writer · Page creation failed",
                message: error.localizedDescription,
                kind: .failure
            )
            await refreshManagerStateAfterFailure()
        }
    }

    private func refreshManagerStateAfterFailure() async {
        if let response = try? await api.siteManager(path: currentPath) {
            applySiteManagerResponse(response)
        }
    }

    private func loadSiteManagerWhenAvailable() async {
        guard !isBusy else {
            waitingForManagerUnlock = true
            return
        }
        waitingForManagerUnlock = false
        await loadSiteManager()
    }

    private func refreshAfterManagerUnlockIfNeeded() {
        guard waitingForManagerUnlock, !isBusy else { return }
        waitingForManagerUnlock = false
        Task { await loadSiteManager() }
    }

    private func loadSiteManager(path: String = "") async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        managerRequestGeneration += 1
        let requestGeneration = managerRequestGeneration
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.siteManager(path: path)
            guard requestGeneration == managerRequestGeneration else { return }
            applySiteManagerResponse(response)
            appState.apiStatus = "Site Manager ready"
            appState.lastAPIError = ""
        } catch {
            setOperationError(error)
        }
    }

    private func applySiteManagerResponse(_ response: [String: Any]) {
        guard let manager = response["manager"] as? [String: Any] else { return }

        let previousDirectory = appState.connectedDirectory
        let nextDirectory: String
        if let directory = manager["directory"] as? [String: Any] {
            nextDirectory = directory["path"] as? String ?? ""
        } else {
            nextDirectory = ""
        }
        if nextDirectory != previousDirectory {
            selectedAssetPath = ""
            selectedImageURL = nil
            selectedImageName = "No image selected"
        }
        appState.connectedDirectory = nextDirectory

        backups = (manager["backups"] as? [[String: Any]] ?? []).compactMap { item in
            guard numericInt(item["id"]) > 0, let filename = item["filename"] as? String else { return nil }
            return SiteBackup(
                id: numericInt(item["id"]),
                filename: filename,
                sizeLabel: item["size_label"] as? String ?? "-",
                fileCount: numericInt(item["file_count"]),
                createdAt: item["created_at"] as? String ?? "",
                exists: item["exists"] as? Bool ?? false
            )
        }

        updates = (manager["updates"] as? [[String: Any]] ?? []).compactMap { item in
            let identifier = numericInt(item["id"])
            guard identifier > 0 else { return nil }
            let changedFiles = (item["files"] as? [[String: Any]] ?? []).compactMap { file -> SiteChangedFile? in
                guard let path = file["path"] as? String else { return nil }
                return SiteChangedFile(path: path, change: file["change"] as? String ?? "changed")
            }
            let snapshotPath = item["snapshot_path"] as? String ?? ""
            return SiteUpdate(
                id: identifier,
                source: item["source"] as? String ?? "Update",
                status: item["status"] as? String ?? "pending",
                summary: item["summary"] as? String ?? "",
                files: changedFiles,
                diffSummary: item["diff_summary"] as? String ?? "",
                hasSnapshot: !snapshotPath.isEmpty,
                createdAt: item["created_at"] as? String ?? ""
            )
        }

        let localMessages = aiChatMessages.filter { $0.id < 0 }
        let remoteMessages: [SiteChatMessage] = (manager["codex_messages"] as? [[String: Any]] ?? []).compactMap { item in
            let identifier = numericInt(item["id"])
            let role = (item["role"] as? String ?? "assistant").lowercased()
            let content = (item["content"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard identifier > 0, !content.isEmpty else { return nil }
            return SiteChatMessage(
                id: identifier,
                role: role,
                content: content,
                createdAt: item["created_at"] as? String ?? ""
            )
        }
        aiChatMessages = remoteMessages + localMessages

        if let browser = manager["files"] as? [String: Any] {
            currentPath = browser["current_path"] as? String ?? ""
            parentPath = browser["parent_path"] as? String ?? ""
            files = (browser["entries"] as? [[String: Any]] ?? []).compactMap { item in
                guard let path = item["path"] as? String, let name = item["name"] as? String else { return nil }
                return SiteFileEntry(
                    path: path,
                    name: name,
                    isDirectory: item["is_dir"] as? Bool ?? false,
                    sizeLabel: item["size_label"] as? String ?? "-",
                    modifiedAt: item["modified_at"] as? String ?? "",
                    previewable: item["previewable"] as? Bool ?? false,
                    isImage: item["is_image"] as? Bool ?? false
                )
            }
        } else {
            currentPath = ""
            parentPath = ""
            files = []
        }

        assets = (manager["assets"] as? [[String: Any]] ?? []).compactMap { item in
            guard let path = item["path"] as? String, let name = item["name"] as? String else { return nil }
            return SiteAsset(path: path, name: name, sizeLabel: item["size_label"] as? String ?? "-")
        }

        if let key = manager["ssh_key"] as? [String: Any] {
            sshKey = SiteSSHKey(
                exists: key["exists"] as? Bool ?? false,
                privatePath: key["private_path"] as? String ?? "",
                publicKey: key["public_key"] as? String ?? "",
                installCommand: key["install_command"] as? String ?? ""
            )
        } else {
            sshKey = SiteSSHKey()
        }

        if let remote = manager["remote_connection"] as? [String: Any] {
            remoteConnected = true
            remoteMatchesDirectory = remote["directory_matches"] as? Bool ?? false
            remoteHasSavedPassword = (remote["has_password"] as? Bool) ?? (numericInt(remote["has_password"]) > 0)
            appState.remoteHost = remote["host"] as? String ?? ""
            remoteUser = remote["username"] as? String ?? ""
            remotePath = remote["remote_path"] as? String ?? ""
            let port = numericInt(remote["port"])
            remotePort = String(port > 0 ? port : 22)
            let configuredKeyPath = remote["key_path"] as? String ?? ""
            sshKeyPath = configuredKeyPath.isEmpty ? sshKey.privatePath : configuredKeyPath
            appState.remoteAuthMethod = (remote["auth_method"] as? String) == "password" ? .password : .sshKey
            savedRemoteDraftIdentity = remoteDraftIdentity
        } else {
            remoteConnected = false
            remoteMatchesDirectory = false
            remoteHasSavedPassword = false
            savedRemoteDraftIdentity = ""
            appState.remoteHost = ""
            remoteUser = ""
            remotePath = ""
            remotePort = "22"
            if sshKey.exists {
                sshKeyPath = sshKey.privatePath
            }
        }

        if let selectedAsset = manager["selected_asset"] as? String, !selectedAsset.isEmpty {
            selectedAssetPath = selectedAsset
        }
    }

    private func testRemoteConnection() async {
        guard !isBusy, remoteDraftIsComplete else { return }

        let host = appState.remoteHost.trimmingCharacters(in: .whitespacesAndNewlines)
        let port = remotePort.trimmingCharacters(in: .whitespacesAndNewlines)
        let username = remoteUser.trimmingCharacters(in: .whitespacesAndNewlines)
        let path = remotePath.trimmingCharacters(in: .whitespacesAndNewlines)
        let keyPath = sshKeyPath.trimmingCharacters(in: .whitespacesAndNewlines)
        let authMethod = appState.remoteAuthMethod == .password ? "password" : "key"
        let password = remotePassword
        let expectedDirectory = appState.connectedDirectory
        let testedFingerprint = remoteDraftFingerprint

        remoteTestInProgress = true
        remoteTestSucceeded = false
        testedRemoteDraftFingerprint = ""
        remoteTestMessage = "Testing SSH access and the remote website path..."
        appState.siteManagerOperationInProgress = true
        defer {
            remoteTestInProgress = false
            appState.siteManagerOperationInProgress = false
        }

        do {
            let response = try await api.testRemoteConnection(
                host: host,
                port: port,
                username: username,
                remotePath: path,
                keyPath: keyPath,
                authMethod: authMethod,
                password: password,
                expectedDirectory: expectedDirectory
            )
            let message = try remoteTestResultMessage(response)
            guard testedFingerprint == remoteDraftFingerprint else {
                remoteTestMessage = "Connection settings changed while the test was running. Test them again."
                return
            }
            remoteTestSucceeded = true
            testedRemoteDraftFingerprint = testedFingerprint
            remoteTestMessage = message
            setOperationSuccess("Remote connection test passed")
        } catch {
            remoteTestMessage = error.localizedDescription
            setOperationError(error)
        }
    }

    private func remoteTestResultMessage(_ response: [String: Any]) throws -> String {
        guard let remoteTest = response["remote_test"] else {
            throw ONEBoardAPIError.invalidResponse
        }
        if let result = remoteTest as? [String: Any] {
            let succeeded = (result["success"] as? Bool) ?? (result["ok"] as? Bool) ?? true
            let message = (result["message"] as? String)
                ?? (result["detail"] as? String)
                ?? "SSH authentication and the remote website path were verified."
            guard succeeded else { throw ONEBoardAPIError.server(message) }
            return message
        }
        if let succeeded = remoteTest as? Bool {
            guard succeeded else { throw ONEBoardAPIError.server("The remote connection test failed.") }
            return "SSH authentication and the remote website path were verified."
        }
        if let message = remoteTest as? String, !message.isEmpty {
            return message
        }
        throw ONEBoardAPIError.invalidResponse
    }

    private func saveRemoteConnection() async {
        guard !isBusy, remoteDraftIsComplete else { return }
        let testedBeforeSave = currentRemoteDraftWasTested
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.saveRemoteConnection(
                host: appState.remoteHost,
                port: remotePort,
                username: remoteUser,
                remotePath: remotePath,
                keyPath: sshKeyPath,
                authMethod: appState.remoteAuthMethod == .password ? "password" : "key",
                password: remotePassword,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            remotePassword = ""
            if testedBeforeSave {
                remoteTestSucceeded = true
                testedRemoteDraftFingerprint = remoteDraftFingerprint
                remoteTestMessage = "SSH authentication and the remote website path were verified."
            }
            setOperationSuccess("Remote connection saved")
        } catch {
            setOperationError(error)
        }
    }

    private func generateSSHKey() async {
        guard !isBusy else { return }
        let draftHost = appState.remoteHost
        let draftPort = remotePort
        let draftUser = remoteUser
        let draftPath = remotePath
        let draftAuthMethod = appState.remoteAuthMethod
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.generateSSHKey()
            applySiteManagerResponse(response)
            if !remoteConnected {
                appState.remoteHost = draftHost
                remotePort = draftPort
                remoteUser = draftUser
                remotePath = draftPath
                appState.remoteAuthMethod = draftAuthMethod
                sshKeyPath = sshKey.privatePath
            }
            setOperationSuccess("SSH key generated")
        } catch {
            setOperationError(error)
        }
    }

    private func syncRemoteSite() async {
        guard !isBusy, currentRemoteDraftWasTested else {
            remoteTestMessage = "Test the current connection settings before downloading the website."
            return
        }
        let password = remotePassword
        let expectedDirectory = appState.connectedDirectory
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let savedResponse = try await api.saveRemoteConnection(
                host: appState.remoteHost,
                port: remotePort,
                username: remoteUser,
                remotePath: remotePath,
                keyPath: sshKeyPath,
                authMethod: appState.remoteAuthMethod == .password ? "password" : "key",
                password: password,
                expectedDirectory: expectedDirectory
            )
            applySiteManagerResponse(savedResponse)
            remotePassword = ""

            let response = try await api.syncRemoteSite(expectedDirectory: expectedDirectory)
            applySiteManagerResponse(response)
            remoteTestSucceeded = false
            testedRemoteDraftFingerprint = ""
            remoteTestMessage = "Remote website downloaded. Edit the managed local workspace, then approve and publish your changes over SSH."
            setOperationSuccess("Remote website connected and downloaded")
        } catch {
            remoteTestSucceeded = false
            testedRemoteDraftFingerprint = ""
            remoteTestMessage = error.localizedDescription
            setOperationError(error)
        }
    }

    private func createBackup() async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.createBackup(expectedDirectory: appState.connectedDirectory)
            applySiteManagerResponse(response)
            setOperationSuccess("Backup created")
        } catch {
            setOperationError(error)
        }
    }

    private func restoreBackup(_ backup: SiteBackup) async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.restoreBackup(
                id: backup.id,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            setOperationSuccess("Backup restored")
        } catch {
            setOperationError(error)
        }
    }

    private func performUpdateAction(_ update: SiteUpdate, action: String) async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.updateAction(
                id: update.id,
                action: action,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            let message: String
            switch action {
            case "approve": message = "Update approved"
            case "publish": message = "Update published to the remote website"
            case "restore": message = "Update files restored"
            default: message = "Update completed"
            }
            setOperationSuccess(message)
        } catch {
            setOperationError(error)
        }
    }

    private func deleteFile(_ file: SiteFileEntry) async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.deleteFile(
                path: file.path,
                expectedDirectory: appState.connectedDirectory
            )
            applySiteManagerResponse(response)
            setOperationSuccess("File deleted")
        } catch {
            setOperationError(error)
        }
    }

    private func runTerminalCommand() async {
        guard !isBusy else { return }
        appState.siteManagerOperationInProgress = true
        defer { appState.siteManagerOperationInProgress = false }
        do {
            let response = try await api.runTerminal(
                command: terminalCommand,
                expectedDirectory: appState.connectedDirectory
            )
            applyTerminalResponse(response)
            setOperationSuccess("Command completed")
        } catch {
            setOperationError(error)
        }
    }

    private func applyTerminalResponse(_ response: [String: Any]) {
        guard let terminal = response["terminal"] as? [String: Any] else { return }
        let command = terminal["command"] as? String ?? terminalCommand
        let output = terminal["output"] as? String ?? ""
        let exitCode = stringify(terminal["exit_code"])
        terminalOutput = "$ \(command)\n\(output)\n\nExit: \(exitCode.isEmpty ? "-" : exitCode)"
    }

    private func openFile(_ file: SiteFileEntry) {
        guard !isBusy else { return }
        guard let url = localURL(relativePath: file.path) else { return }
        NSWorkspace.shared.open(url)
    }

    private func revealCurrentDirectory() {
        guard !isBusy else { return }
        guard let url = localURL(relativePath: currentPath) else { return }
        NSWorkspace.shared.open(url)
    }

    private func localURL(relativePath: String) -> URL? {
        guard !appState.connectedDirectory.isEmpty else { return nil }
        let root = URL(fileURLWithPath: appState.connectedDirectory, isDirectory: true).standardizedFileURL
        let candidate = root.appendingPathComponent(relativePath).standardizedFileURL
        guard candidate.path == root.path || candidate.path.hasPrefix(root.path + "/") else { return nil }
        return candidate
    }

    private func copyToClipboard(_ value: String) {
        guard !value.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(value, forType: .string)
        managerMessage = "Copied to clipboard"
    }

    private func setOperationSuccess(_ message: String) {
        managerMessage = message
        appState.apiStatus = message
        appState.lastAPIError = ""
    }

    private func setOperationError(_ error: Error) {
        managerMessage = ""
        appState.lastAPIError = error.localizedDescription
        appState.apiStatus = "Site Manager needs attention"
    }

    private func appendLocalChat(role: String, content: String) {
        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        localChatSeed -= 1
        aiChatMessages.append(
            SiteChatMessage(
                id: localChatSeed,
                role: role,
                content: trimmed,
                createdAt: DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .short)
            )
        )
    }

    private func messageBubble(_ message: SiteChatMessage, isAssistant: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(isAssistant ? "Assistant" : "You")
                .font(.caption2.weight(.bold))
                .foregroundStyle(isAssistant ? ONEBoardTheme.muted : ONEBoardTheme.success)
            Text(message.content)
                .font(.callout)
                .foregroundStyle(ONEBoardTheme.ink)
                .textSelection(.enabled)
            if !message.createdAt.isEmpty {
                Text(message.createdAt)
                    .font(.caption2)
                    .foregroundStyle(ONEBoardTheme.faint)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            isAssistant
                ? Color.white.opacity(0.05)
                : ONEBoardTheme.brand.opacity(0.17),
            in: RoundedRectangle(cornerRadius: 12, style: .continuous)
        )
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(isAssistant ? Color.white.opacity(0.10) : ONEBoardTheme.brand.opacity(0.30), lineWidth: 1)
        }
    }

    private func typingBubble(text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            ProgressView()
                .controlSize(.small)
            Text(text)
                .font(.caption)
                .foregroundStyle(ONEBoardTheme.muted)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.10), lineWidth: 1)
        }
    }

    private func confirmationAlert(for action: SiteManagerDestructiveAction) -> Alert {
        switch action {
        case .deleteFile(let file):
            return Alert(
                title: Text("Delete \(file.name)?"),
                message: Text("This permanently removes the file from the connected website directory."),
                primaryButton: .destructive(Text("Delete")) { Task { await deleteFile(file) } },
                secondaryButton: .cancel()
            )
        case .restoreBackup(let backup):
            return Alert(
                title: Text("Restore this backup?"),
                message: Text("The current website directory will be replaced by \(backup.filename)."),
                primaryButton: .destructive(Text("Restore")) { Task { await restoreBackup(backup) } },
                secondaryButton: .cancel()
            )
        case .restoreUpdate(let update):
            return Alert(
                title: Text("Restore files from update #\(update.id)?"),
                message: Text("Files changed by this update will be restored from its snapshot."),
                primaryButton: .destructive(Text("Restore")) { Task { await performUpdateAction(update, action: "restore") } },
                secondaryButton: .cancel()
            )
        case .publishUpdate(let update):
            return Alert(
                title: Text("Publish update #\(update.id)?"),
                message: Text("ONEBoard will verify and publish the approved local website to \(remoteDestinationLabel). Confirm that this is the intended production destination."),
                primaryButton: .destructive(Text("Publish")) { Task { await performUpdateAction(update, action: "publish") } },
                secondaryButton: .cancel()
            )
        case .syncRemote:
            return Alert(
                title: Text("Connect and download this remote website?"),
                message: Text("ONEBoard will save the tested SSH settings and download \(remoteDestinationLabel) into its managed local workspace. Refreshing it can replace that managed copy; other local website folders are not affected."),
                primaryButton: .destructive(Text("Connect & Download")) { Task { await syncRemoteSite() } },
                secondaryButton: .cancel()
            )
        case .applyAIUpdate:
            return Alert(
                title: Text("Apply AI website update?"),
                message: Text("ONEBoard will apply the update with \(siteProviderLabel(selectedAIProvider)) · \(selectedAIModel) and then save it for review/publish.\n\nTip: generate a plan first if you want a preview of the procedure."),
                primaryButton: .destructive(Text("Apply Update")) { Task { await runAIUpdate(promptOverride: proposedPlanPrompt.isEmpty ? nil : proposedPlanPrompt) } },
                secondaryButton: .cancel()
            )
        }
    }
}

enum QuickPrompt: String {
    case hero = "Update the homepage hero section with stronger positioning and a clearer call to action."
    case section = "Add a useful section that matches the existing website style."
    case cta = "Improve the primary call to action across the page."
    case landing = "Create a focused landing page using the existing design system."
}

struct SecurityScanNativeView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared
    @State private var domain = ""
    @State private var history: [ScanHistoryItem] = []
    @State private var latestScan: [String: Any] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            NativeCard(title: "Passive Security Scan", systemImage: "shield.checkered") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        TextField("example.com", text: $domain)
                        Button("Analyze Domain") {
                            Task { await runScan() }
                        }
                            .buttonStyle(.borderedProminent)
                    }
                    Text("Reviews DNS, HTTPS response, TLS certificate, HSTS, security headers, exposed technology, recommendations, and scan history.")
                        .foregroundStyle(ONEBoardTheme.muted)
                }
            }

            NativeCard(title: "Scan History", systemImage: "clock") {
                VStack(spacing: 10) {
                    if history.isEmpty {
                        Text("No scans have been run yet.")
                            .foregroundStyle(ONEBoardTheme.muted)
                    }
                    ForEach(history) { item in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(item.domain)
                                    .font(.headline)
                                Text(item.date)
                                    .foregroundStyle(ONEBoardTheme.muted)
                            }
                            Spacer()
                            Text(item.score)
                                .font(.title2.bold())
                            Text(item.grade)
                                .font(.headline)
                            Text(item.change)
                                .foregroundStyle(item.change.hasPrefix("-") ? Color(red: 1, green: 112 / 255, blue: 112 / 255) : ONEBoardTheme.success)
                        }
                        Divider()
                            .overlay(ONEBoardTheme.line)
                    }
                }
            }

            LazyVGrid(columns: gridColumns, spacing: 16) {
                NativeCard(title: "TLS", systemImage: "lock.shield") {
                    ScanDetailRows(rows: tlsRows)
                }

                NativeCard(title: "DNS", systemImage: "network") {
                    ScanDetailRows(rows: dnsRows)
                }

                NativeCard(title: "HTTP Security Headers", systemImage: "list.bullet.rectangle") {
                    FlowLayout(items: headerRows)
                }

                NativeCard(title: "Recommendations", systemImage: "checklist") {
                    VStack(alignment: .leading, spacing: 8) {
                        if recommendations.isEmpty {
                            Text("Run a scan to receive recommendations.")
                                .foregroundStyle(ONEBoardTheme.muted)
                        }
                        ForEach(recommendations, id: \.title) { recommendation in
                            RecommendationRow(priority: recommendation.priority, title: recommendation.title)
                        }
                    }
                }
            }
        }
        .task {
            await loadHistory()
        }
    }

    private func loadHistory() async {
        do {
            let response = try await api.securityScanHistory()
            applyHistory(response)
            appState.apiStatus = "Connected to ONEBoard service"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func runScan() async {
        do {
            let response = try await api.runSecurityScan(domain: domain)
            latestScan = response["scan"] as? [String: Any] ?? [:]
            applyHistory(response)
            appState.apiStatus = "Security scan complete"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private var tlsRows: [(String, String)] {
        let tls = latestScan["tls"] as? [String: Any] ?? [:]
        return [
            ("Certificate", stringify(tls["valid"]) == "1" || (tls["valid"] as? Bool == true) ? "Valid" : "Unavailable"),
            ("Issuer", stringify(tls["issuer"])),
            ("Protocol", stringify(tls["protocol"])),
            ("Expiration", stringify(tls["expires"])),
            ("HSTS", tls["hsts"] as? Bool == true ? "Active" : "Missing"),
        ]
    }

    private var dnsRows: [(String, String)] {
        let dns = latestScan["dns"] as? [String: Any] ?? [:]
        let addresses = (dns["addresses"] as? [String] ?? []).joined(separator: ", ")
        return [
            ("Resolution", dns["reachable"] as? Bool == true ? "Correct" : "Failed"),
            ("Addresses", addresses.isEmpty ? "None" : addresses),
        ]
    }

    private var headerRows: [String] {
        let http = latestScan["http"] as? [String: Any] ?? [:]
        let present = http["security_headers"] as? [String] ?? []
        let missing = (http["missing_headers"] as? [String] ?? []).map { "\($0) missing" }
        return present + missing
    }

    private var recommendations: [(priority: String, title: String)] {
        (latestScan["recommendations"] as? [[String: Any]] ?? []).map {
            (stringify($0["priority_label"]), stringify($0["title"]))
        }
    }

    private func applyHistory(_ response: [String: Any]) {
        let scanHistory = response["scan_history"] as? [String: Any] ?? [:]
        history = (scanHistory["latest"] as? [[String: Any]] ?? []).map {
            ScanHistoryItem(
                domain: stringify($0["domain"]),
                date: stringify($0["created_at"]),
                score: stringify($0["score"]),
                grade: stringify($0["grade"]),
                change: stringify($0["change_label"])
            )
        }
    }
}

struct SettingsNativeView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var api = ONEBoardAPI.shared
    @State private var openAIKey = ""
    @State private var anthropicKey = ""
    @State private var openRouterKey = ""
    @State private var googleKey = ""
    @State private var currentPassword = ""
    @State private var selectedProvider = "openai"
    @State private var selectedModel = ""
    @State private var selectedTaskType = "assistant"
    @State private var providerModels: [String: [String]] = [
        "openai": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-5-mini", "gpt-5"],
        "anthropic": ["claude-sonnet-4", "claude-3-5-haiku"],
        "openrouter": ["openai/gpt-5", "anthropic/claude-sonnet-4", "google/gemini-2.5-pro"],
        "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
    ]
    @State private var aiPrompt = ""
    @State private var aiContext = ""
    @State private var aiOutput = ""
    @State private var aiRuns: [[String: Any]] = []
    @State private var aiRunning = false
    @State private var accountName = ""
    @State private var companyName = "ONEBoard"
    @State private var companyEmail = "Unknown_4792@proton.me"
    @State private var companyWebsite = ""
    @State private var language = "Spanish"
    @State private var newPassword = ""
    @State private var confirmPassword = ""

    var body: some View {
        LazyVGrid(columns: gridColumns, spacing: 16) {
            NativeCard(title: "Profile", systemImage: "person.crop.circle") {
                VStack(alignment: .leading, spacing: 10) {
                    Picker("Language", selection: $language) {
                        Text("Spanish").tag("Spanish")
                        Text("English").tag("English")
                    }
                    TextField("Name", text: $accountName)
                }
            }

            NativeCard(title: "Company", systemImage: "building.2") {
                VStack(alignment: .leading, spacing: 10) {
                    TextField("Company name", text: $companyName)
                    TextField("Company email", text: $companyEmail)
                    TextField("Company website", text: $companyWebsite)
                    Button("Save Profile") {
                        Task { await saveAccount() }
                    }
                    .buttonStyle(.bordered)
                }
            }

            NativeCard(title: "Security", systemImage: "lock") {
                VStack(alignment: .leading, spacing: 10) {
                    SecureField("Current password", text: $currentPassword)
                    SecureField("New password", text: $newPassword)
                    SecureField("Confirm new password", text: $confirmPassword)
                    Button("Update Password") {
                        Task { await saveAccount() }
                    }
                    .buttonStyle(.bordered)
                }
            }

            NativeCard(title: "AI Providers", systemImage: "key") {
                VStack(alignment: .leading, spacing: 10) {
                    Picker("Provider", selection: $selectedProvider) {
                        ForEach(providerModels.keys.sorted(), id: \.self) { provider in
                            Text(providerLabel(provider)).tag(provider)
                        }
                    }

                    Picker("Model", selection: $selectedModel) {
                        ForEach(modelsForSelectedProvider, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }

                    Divider()

                    SecureField("OpenAI API key", text: $openAIKey)
                    SecureField("Anthropic API key", text: $anthropicKey)
                    SecureField("OpenRouter API key", text: $openRouterKey)
                    SecureField("Google AI API key", text: $googleKey)
                    SecureField("Current password", text: $currentPassword)

                    Toggle("OpenAI key saved", isOn: $appState.openAIKeySaved)

                    Text("Production build should save these secrets in macOS Keychain before App Store submission.")
                        .foregroundStyle(ONEBoardTheme.muted)

                    HStack(spacing: 10) {
                        Button("Save Credentials") {
                            Task { await saveAICredentials() }
                        }
                        .buttonStyle(.borderedProminent)

                        Button("Save Policy") {
                            Task { await saveAIPolicy() }
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }

            NativeCard(title: "AI Playground", systemImage: "sparkles.rectangle.stack") {
                VStack(alignment: .leading, spacing: 10) {
                    Picker("Task type", selection: $selectedTaskType) {
                        Text("Assistant").tag("assistant")
                        Text("SEO Brief").tag("seo_brief")
                        Text("Content Brief").tag("content_brief")
                    }

                    Text("Prompt")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(ONEBoardTheme.muted)
                    TextEditor(text: $aiPrompt)
                        .frame(minHeight: 110)
                        .padding(8)
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                    Text("Context")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(ONEBoardTheme.muted)
                    TextEditor(text: $aiContext)
                        .frame(minHeight: 72)
                        .padding(8)
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                    Button(aiRunning ? "Running..." : "Run AI Task") {
                        Task { await runAIPlayground() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(aiRunning || aiPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selectedModel.isEmpty)

                    if !aiOutput.isEmpty {
                        Text("Latest response")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(ONEBoardTheme.muted)
                        ScrollView {
                            Text(aiOutput)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .foregroundStyle(ONEBoardTheme.ink)
                        }
                        .frame(minHeight: 120, maxHeight: 220)
                        .padding(10)
                        .background(Color.black.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }

                    if !aiRuns.isEmpty {
                        Text("Recent runs")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(ONEBoardTheme.muted)
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(Array(aiRuns.prefix(5).enumerated()), id: \.offset) { _, run in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("\((run["provider"] as? String ?? "AI").uppercased()) · \(run["model"] as? String ?? "")")
                                        .font(.caption.weight(.bold))
                                        .foregroundStyle(ONEBoardTheme.ink)
                                    Text(run["task_type"] as? String ?? "assistant")
                                        .font(.caption)
                                        .foregroundStyle(ONEBoardTheme.brand)
                                    Text(run["response_text"] as? String ?? run["error_text"] as? String ?? "")
                                        .font(.caption)
                                        .foregroundStyle(ONEBoardTheme.muted)
                                        .lineLimit(3)
                                }
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            }
                        }
                    }
                }
            }

            NativeCard(title: "Google Search Console", systemImage: "magnifyingglass") {
                VStack(alignment: .leading, spacing: 8) {
                    LabeledContent("Client ID", value: "Configured on server")
                    LabeledContent("Client Secret", value: "Configured privately")
                    LabeledContent("Redirect URI", value: "Local loopback callback (assigned when ONEBoard starts)")
                    Button("Connect Google") {
                        Task { await connectGoogle() }
                    }
                        .buttonStyle(.borderedProminent)
                }
            }

            NativeCard(title: "Website Directory", systemImage: "folder") {
                VStack(alignment: .leading, spacing: 10) {
                    Text(appState.connectedDirectory.isEmpty ? "No website folder connected" : appState.connectedDirectory)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(appState.connectedDirectory.isEmpty ? ONEBoardTheme.muted : ONEBoardTheme.ink)
                        .lineLimit(2)
                    Text("Website folders are connected and validated in Site Manager.")
                        .font(.caption)
                        .foregroundStyle(ONEBoardTheme.muted)
                    Button("Open Site Manager") {
                        appState.selectedSection = .siteManager
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .task {
            await loadAISettings()
            await loadAIRuns()
            await loadAccount()
        }
        .onChange(of: selectedProvider) { _, newProvider in
            let models = providerModels[newProvider] ?? []
            if !models.contains(selectedModel) {
                selectedModel = models.first ?? ""
            }
        }
    }

    private var modelsForSelectedProvider: [String] {
        providerModels[selectedProvider] ?? []
    }

    private func providerLabel(_ provider: String) -> String {
        switch provider {
        case "openai":
            return "OpenAI"
        case "anthropic":
            return "Anthropic"
        case "openrouter":
            return "OpenRouter"
        case "google":
            return "Google"
        default:
            return provider.capitalized
        }
    }

    private func connectGoogle() async {
        do {
            let url = try await api.createSearchConsoleConnection()
            _ = await MainActor.run {
                NSWorkspace.shared.open(url)
            }
            appState.apiStatus = "Google authorization opened"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func saveAPIKey() async {
        do {
            _ = try await api.saveOpenAIKey(openAIKey, currentPassword: currentPassword)
            appState.openAIKeySaved = !openAIKey.isEmpty
            appState.apiStatus = "OpenAI API key updated"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func saveAICredentials() async {
        do {
            let response = try await api.saveAICredentials(
                currentPassword: currentPassword,
                openAIKey: openAIKey,
                anthropicKey: anthropicKey,
                openRouterKey: openRouterKey,
                googleKey: googleKey
            )
            if let credentials = response["credentials"] as? [String: Any] {
                appState.openAIKeySaved = credentials["openai"] as? Bool ?? false
            }
            appState.apiStatus = "AI credentials updated"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func saveAIPolicy() async {
        do {
            _ = try await api.saveAIPolicy(provider: selectedProvider, model: selectedModel)
            appState.apiStatus = "AI policy updated"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func loadAccount() async {
        do {
            let response = try await api.settings()
            guard let account = response["account"] as? [String: Any] else { return }
            accountName = stringify(account["name"])
            companyName = stringify(account["company_name"])
            companyEmail = stringify(account["company_email"])
            companyWebsite = stringify(account["company_website"])
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func saveAccount() async {
        do {
            _ = try await api.saveAccount(
                name: accountName,
                companyName: companyName,
                companyEmail: companyEmail,
                companyWebsite: companyWebsite,
                currentPassword: currentPassword,
                newPassword: newPassword,
                confirmPassword: confirmPassword
            )
            newPassword = ""
            confirmPassword = ""
            currentPassword = ""
            appState.apiStatus = "Account settings updated"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func runAIPlayground() async {
        aiRunning = true
        defer { aiRunning = false }
        do {
            let response = try await api.runAI(
                taskType: selectedTaskType,
                provider: selectedProvider,
                model: selectedModel,
                prompt: aiPrompt,
                context: aiContext
            )
            if let run = response["run"] as? [String: Any] {
                aiOutput = run["response_text"] as? String ?? ""
            }
            if let runs = response["runs"] as? [[String: Any]] {
                aiRuns = runs
            }
            appState.apiStatus = "AI task complete"
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func loadAIRuns() async {
        do {
            let response = try await api.aiRuns()
            if let runs = response["runs"] as? [[String: Any]] {
                aiRuns = runs
            }
            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }

    private func loadAISettings() async {
        do {
            let response = try await api.aiSettings()
            if let providers = response["providers"] as? [[String: Any]] {
                var discovered: [String: [String]] = [:]
                for provider in providers {
                    guard let key = provider["key"] as? String else { continue }
                    let models = provider["models"] as? [String] ?? []
                    discovered[key] = models
                }
                if !discovered.isEmpty {
                    providerModels = discovered
                }
            }

            if let policy = response["policy"] as? [String: Any] {
                let provider = (policy["provider"] as? String ?? "openai").lowercased()
                if providerModels[provider] != nil {
                    selectedProvider = provider
                }
                let model = policy["model"] as? String ?? ""
                if (providerModels[selectedProvider] ?? []).contains(model) {
                    selectedModel = model
                }
            }

            if selectedModel.isEmpty {
                selectedModel = providerModels[selectedProvider]?.first ?? ""
            }

            if let credentials = response["credentials"] as? [String: Any] {
                appState.openAIKeySaved = credentials["openai"] as? Bool ?? false
            }

            appState.lastAPIError = ""
        } catch {
            appState.lastAPIError = error.localizedDescription
        }
    }
}

struct HelpNativeView: View {
    private let topics = [
        ("Dashboard", "Connect Search Console, choose a property, review clicks, impressions, CTR, position, top keywords, traffic pages, charts, and SEO opportunities."),
        ("Site Manager", "Connect a local folder, create backups, run AI website updates, upload client images, review diffs, approve, publish, restore, and manage files."),
        ("Remote Deploy", "Configure SSH/SFTP with key or password, test the connection, publish approved updates, and keep remote paths separated from local paths."),
        ("Security Scan", "Run passive checks for DNS, HTTPS, TLS, HSTS, HTTP security headers, exposed technology, recommendations, and scan history."),
        ("AI Setup", "Each user enters their own OpenAI API key. The native app should store secrets in Keychain before App Store submission."),
        ("Google Setup", "Google OAuth credentials remain private. The app uses Search Console authorization to read organic performance data."),
        ("Content Creation", "Use Search Console opportunities, SEO Writer, quick prompts, and optional uploaded images to create useful site content faster."),
        ("Developer Contact", "Roberto Castillo · 7378081326 · Unknown_4792@proton.me")
    ]

    var body: some View {
        LazyVGrid(columns: gridColumns, spacing: 16) {
            ForEach(topics, id: \.0) { topic in
                NativeCard(title: topic.0, systemImage: topic.0 == "Developer Contact" ? "person.crop.circle.badge.questionmark" : "questionmark.circle") {
                    Text(topic.1)
                        .foregroundStyle(ONEBoardTheme.muted)
                }
            }
        }
    }
}

struct SearchConsoleSite: Identifiable, Hashable {
    let siteURL: String
    let permissionLevel: String

    var id: String { siteURL }
    var displayName: String { siteURL }

    var canReadAnalytics: Bool {
        ["siteOwner", "siteFullUser", "siteRestrictedUser"].contains(permissionLevel)
    }

    var permissionLabel: String {
        switch permissionLevel {
        case "siteOwner": "Owner access"
        case "siteFullUser": "Full access"
        case "siteRestrictedUser": "Restricted access"
        case "siteUnverifiedUser": "Unverified property"
        default: "Unknown access"
        }
    }

    var menuLabel: String {
        "\(displayName) · \(permissionLabel)"
    }
}

struct SearchMetric: Identifiable {
    let id = UUID()
    let label: String
    let value: String
    let detail: String
}

struct SearchChartEntry: Identifiable {
    let id = UUID()
    let label: String
    let display: String
    let percent: Int
}

struct SearchRow: Identifiable {
    let id = UUID()
    let key: String
    let clicks: String
    let impressions: String
    let ctr: String
    let position: String
}

struct PageRow: Identifiable {
    let id = UUID()
    let url: String
    let clicks: String
    let impressions: String
    let position: String
}

struct SeoOpportunity: Identifiable {
    let id = UUID()
    let title: String
    let keyword: String
    let impressions: String
    let clicks: String
    let position: String
}

struct SiteBackup: Identifiable {
    let id: Int
    let filename: String
    let sizeLabel: String
    let fileCount: Int
    let createdAt: String
    let exists: Bool
}

struct SiteChangedFile: Identifiable {
    var id: String { "\(change):\(path)" }
    let path: String
    let change: String
    var label: String { "\(change): \(path)" }
}

struct SiteUpdate: Identifiable {
    let id: Int
    let source: String
    let status: String
    let summary: String
    let files: [SiteChangedFile]
    let diffSummary: String
    let hasSnapshot: Bool
    let createdAt: String
}

struct SiteFileEntry: Identifiable {
    var id: String { path }
    let path: String
    let name: String
    let isDirectory: Bool
    let sizeLabel: String
    let modifiedAt: String
    let previewable: Bool
    let isImage: Bool
}

struct SiteAsset: Identifiable {
    var id: String { path }
    let path: String
    let name: String
    let sizeLabel: String
}

struct SiteChatMessage: Identifiable {
    let id: Int
    let role: String
    let content: String
    let createdAt: String
}

struct SiteSSHKey {
    var exists = false
    var privatePath = ""
    var publicKey = ""
    var installCommand = ""
}

enum SiteManagerDestructiveAction: Identifiable {
    case deleteFile(SiteFileEntry)
    case restoreBackup(SiteBackup)
    case restoreUpdate(SiteUpdate)
    case publishUpdate(SiteUpdate)
    case syncRemote
    case applyAIUpdate

    var id: String {
        switch self {
        case .deleteFile(let file): "delete-file-\(file.id)"
        case .restoreBackup(let backup): "restore-backup-\(backup.id)"
        case .restoreUpdate(let update): "restore-update-\(update.id)"
        case .publishUpdate(let update): "publish-update-\(update.id)"
        case .syncRemote: "sync-remote"
        case .applyAIUpdate: "apply-ai-update"
        }
    }
}

struct ScanHistoryItem: Identifiable {
    let id = UUID()
    let domain: String
    let date: String
    let score: String
    let grade: String
    let change: String
}

struct MetricTile: View {
    let metric: SearchMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(metric.label.uppercased())
                    .font(.caption2.weight(.bold))
                    .tracking(0.8)
                    .foregroundStyle(ONEBoardTheme.muted)
                Spacer()
                Circle()
                    .fill(ONEBoardTheme.brand)
                    .frame(width: 6, height: 6)
                    .shadow(color: ONEBoardTheme.brand.opacity(0.75), radius: 5)
            }
            Text(metric.value)
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(ONEBoardTheme.ink)
            Text(metric.detail)
                .font(.caption)
                .foregroundStyle(ONEBoardTheme.muted)
        }
        .padding(15)
        .frame(maxWidth: .infinity, alignment: .leading)
        .oneBoardGlass(cornerRadius: 16, strong: true)
    }
}

struct StatusTile: View {
    let label: String
    let value: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label.uppercased())
                .font(.caption2.weight(.bold))
                .tracking(0.7)
                .foregroundStyle(ONEBoardTheme.muted)
            Text(value)
                .font(.system(.headline, design: .rounded, weight: .bold))
                .foregroundStyle(ONEBoardTheme.ink)
            Text(detail)
                .font(.caption)
                .foregroundStyle(ONEBoardTheme.muted)
                .lineLimit(2)
        }
        .padding(15)
        .frame(maxWidth: .infinity, alignment: .leading)
        .oneBoardGlass(cornerRadius: 16, strong: true)
    }
}

struct BarRow: View {
    let label: String
    let value: String
    let percent: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label)
                    .lineLimit(1)
                Spacer()
                Text(value)
                    .font(.headline)
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(LinearGradient(colors: [ONEBoardTheme.brand, ONEBoardTheme.success], startPoint: .leading, endPoint: .trailing))
                        .frame(width: proxy.size.width * min(percent, 100) / 100)
                        .shadow(color: ONEBoardTheme.brand.opacity(0.34), radius: 5)
                }
            }
            .frame(height: 8)
        }
    }
}

struct StatPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(ONEBoardTheme.muted)
            Text(value)
                .font(.headline)
                .foregroundStyle(ONEBoardTheme.ink)
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 8)
        .background(ONEBoardTheme.brand.opacity(0.11))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(ONEBoardTheme.brand.opacity(0.15), lineWidth: 1)
        }
    }
}

struct SearchTable: View {
    let title: String
    let rows: [SearchRow]

    var body: some View {
        NativeCard(title: title, systemImage: "tablecells") {
            VStack(alignment: .leading, spacing: 8) {
                TableHeader(columns: ["Keyword", "Clicks", "Impr.", "CTR", "Pos."])
                ForEach(rows) { row in
                    TableLine(values: [row.key, row.clicks, row.impressions, row.ctr, row.position])
                }
            }
        }
    }
}

struct PageTable: View {
    let title: String
    let rows: [PageRow]

    var body: some View {
        NativeCard(title: title, systemImage: "tablecells") {
            VStack(alignment: .leading, spacing: 8) {
                TableHeader(columns: ["Page", "Clicks", "Impr.", "Pos."])
                ForEach(rows) { row in
                    TableLine(values: [row.url, row.clicks, row.impressions, row.position])
                }
            }
        }
    }
}

struct TableHeader: View {
    let columns: [String]

    var body: some View {
        HStack {
            ForEach(Array(columns.enumerated()), id: \.offset) { index, column in
                Text(column)
                    .font(.caption.bold())
                    .foregroundStyle(ONEBoardTheme.muted)
                    .frame(maxWidth: .infinity, alignment: index == 0 ? .leading : .trailing)
            }
        }
    }
}

struct TableLine: View {
    let values: [String]

    var body: some View {
        HStack {
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                Text(value)
                    .lineLimit(1)
                    .font(index == 0 ? .body : .body.monospacedDigit())
                    .foregroundStyle(index == 0 ? ONEBoardTheme.ink : ONEBoardTheme.muted)
                    .frame(maxWidth: .infinity, alignment: index == 0 ? .leading : .trailing)
            }
        }
        Divider()
            .overlay(ONEBoardTheme.line)
    }
}

struct ScanDetailRows: View {
    let rows: [(String, String)]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(rows, id: \.0) { row in
                LabeledContent(row.0, value: row.1)
                    .foregroundStyle(ONEBoardTheme.ink)
                Divider()
                    .overlay(ONEBoardTheme.line)
            }
        }
    }
}

struct FlowLayout: View {
    let items: [String]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.caption)
                    .foregroundStyle(item.contains("missing") ? Color(red: 1, green: 160 / 255, blue: 160 / 255) : ONEBoardTheme.success)
                    .padding(.vertical, 6)
                    .padding(.horizontal, 8)
                    .background(item.contains("missing") ? Color.red.opacity(0.14) : ONEBoardTheme.success.opacity(0.11))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .stroke(item.contains("missing") ? Color.red.opacity(0.22) : ONEBoardTheme.success.opacity(0.20), lineWidth: 1)
                    }
            }
        }
    }
}

struct RecommendationRow: View {
    let priority: String
    let title: String

    var body: some View {
        HStack {
            Text(priority)
                .font(.caption.bold())
                .foregroundStyle(ONEBoardTheme.warning)
                .padding(.vertical, 4)
                .padding(.horizontal, 7)
                .background(ONEBoardTheme.warning.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            Text(title)
                .foregroundStyle(ONEBoardTheme.ink)
            Spacer()
        }
    }
}

let gridColumns = [
    GridItem(.adaptive(minimum: 360), spacing: 16)
]

let compactGridColumns = [
    GridItem(.adaptive(minimum: 220), spacing: 12)
]
