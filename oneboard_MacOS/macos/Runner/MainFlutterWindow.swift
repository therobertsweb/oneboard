import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let windowFrame = self.frame
    self.contentViewController = flutterViewController
    self.setFrame(windowFrame, display: true)
    self.title = "OneBoard"
    self.titlebarAppearsTransparent = true
    self.backgroundColor = NSColor(calibratedRed: 0.965, green: 0.969, blue: 0.988, alpha: 1)
    self.contentMinSize = NSSize(width: 1000, height: 700)
    self.setContentSize(NSSize(width: 1320, height: 860))
    self.center()

    RegisterGeneratedPlugins(registry: flutterViewController)

    let channel = FlutterMethodChannel(
      name: "com.oneboard.flutter/service",
      binaryMessenger: flutterViewController.engine.binaryMessenger
    )
    channel.setMethodCallHandler { call, result in
      guard let appDelegate = NSApp.delegate as? AppDelegate else {
        result(FlutterError(code: "service_unavailable", message: "ONEBoard is unavailable.", details: nil))
        return
      }
      switch call.method {
      case "startService":
        Task {
          do {
            result(try await appDelegate.startONEBoardService())
          } catch {
            result(FlutterError(code: "service_start_failed", message: error.localizedDescription, details: nil))
          }
        }
      case "openExternalURL":
        guard let value = call.arguments as? String else {
          result(FlutterError(code: "invalid_url", message: "The URL is invalid.", details: nil))
          return
        }
        result(appDelegate.openExternalURL(value))
      case "chooseFile":
        result(appDelegate.chooseFile())
      case "chooseDirectory":
        result(appDelegate.chooseDirectory())
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    super.awakeFromNib()
  }
}

