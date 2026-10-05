import Foundation
import Capacitor
import ReplayKit
import UIKit

/// Bildschirm-Freigabe: Startet die System-Übertragung (ReplayKit). Die Broadcast-
/// Extension (native/BroadcastExtension) legt alle ~2 s ein JPEG im App-Group-Container
/// ab; die App liest es hier. So sieht der Tutor eine GoodNotes-Seite im Split View,
/// ohne dass sie exportiert werden muss.
@objc(ScreenSharePlugin)
public class ScreenSharePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ScreenSharePlugin"
    public let jsName = "ScreenShare"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "startBroadcast", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "latestFrame", returnType: CAPPluginReturnPromise)
    ]

    /// Muss zu den Capabilities (App Groups) von App und Extension passen.
    static let appGroup = "group.de.tutor.app"
    /// Bundle-ID der Broadcast-Upload-Extension.
    static let extensionBundleId = "de.tutor.app.Broadcast"

    @objc func startBroadcast(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard let host = self.bridge?.viewController?.view else {
                call.reject("Kein Fenster vorhanden.")
                return
            }
            let picker = RPSystemBroadcastPickerView(frame: CGRect(x: 0, y: 0, width: 44, height: 44))
            picker.preferredExtension = Self.extensionBundleId
            picker.showsMicrophoneButton = false
            picker.alpha = 0.011                       // unsichtbar, muss aber im Fenster hängen
            host.addSubview(picker)
            for case let button as UIButton in picker.subviews {
                button.sendActions(for: .touchUpInside)
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { picker.removeFromSuperview() }
            call.resolve()
        }
    }

    @objc func latestFrame(_ call: CAPPluginCall) {
        guard let dir = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: Self.appGroup) else {
            call.reject("App Group „\(Self.appGroup)“ fehlt (Signing & Capabilities).")
            return
        }
        let versionText = (try? String(contentsOf: dir.appendingPathComponent("frame.version"), encoding: .utf8)) ?? "0"
        let version = Int(versionText.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
        let since = call.getInt("since") ?? 0
        if version == 0 || version == since {
            call.resolve(["version": version])         // nichts Neues → keine Daten übertragen
            return
        }
        guard let data = try? Data(contentsOf: dir.appendingPathComponent("frame.jpg")) else {
            call.resolve(["version": since])
            return
        }
        call.resolve(["version": version, "data": data.base64EncodedString()])
    }
}
