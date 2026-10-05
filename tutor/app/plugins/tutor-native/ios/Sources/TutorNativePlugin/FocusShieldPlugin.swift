import Foundation
import Capacitor
import SwiftUI
import UIKit
#if canImport(FamilyControls)
import FamilyControls
import ManagedSettings
#endif

/// Fokus-Sperre über die Screen-Time-API: Während einer Fokus-Sitzung werden die
/// vom Lernenden gewählten Apps und Webseiten abgeschirmt (Instagram, YouTube, …).
///
/// Voraussetzungen: echtes Gerät, iOS 16+, Capability „Family Controls“ (Apple muss
/// das Entitlement `com.apple.developer.family-controls` für die App-ID freigeben).
@objc(FocusShieldPlugin)
public class FocusShieldPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FocusShieldPlugin"
    public let jsName = "FocusShield"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "requestAuthorization", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "pickApps", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "start", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stop", returnType: CAPPluginReturnPromise)
    ]

    private static let unavailable = "Die Fokus-Sperre braucht iOS 16 oder neuer auf einem echten Gerät."

    @objc func status(_ call: CAPPluginCall) {
        #if canImport(FamilyControls)
        if #available(iOS 16.0, *) {
            call.resolve(["authorized": ShieldController.shared.authorized,
                          "hasSelection": ShieldController.shared.hasSelection])
            return
        }
        #endif
        call.reject(Self.unavailable)
    }

    @objc func requestAuthorization(_ call: CAPPluginCall) {
        #if canImport(FamilyControls)
        if #available(iOS 16.0, *) {
            Task {
                do {
                    try await ShieldController.shared.authorize()
                    call.resolve(["authorized": ShieldController.shared.authorized])
                } catch {
                    call.reject("Freigabe nicht erteilt: \(error.localizedDescription)")
                }
            }
            return
        }
        #endif
        call.reject(Self.unavailable)
    }

    @objc func pickApps(_ call: CAPPluginCall) {
        #if canImport(FamilyControls)
        if #available(iOS 16.0, *) {
            DispatchQueue.main.async {
                guard let presenter = self.bridge?.viewController else {
                    call.reject("Kein Fenster zum Anzeigen.")
                    return
                }
                let picker = PickerView(selection: ShieldController.shared.selection) { selection in
                    ShieldController.shared.selection = selection
                    presenter.dismiss(animated: true) {
                        call.resolve(["hasSelection": ShieldController.shared.hasSelection])
                    }
                }
                let host = UIHostingController(rootView: picker)
                host.isModalInPresentation = true   // nur über „Fertig“ schließen → Promise wird immer aufgelöst
                presenter.present(host, animated: true)
            }
            return
        }
        #endif
        call.reject(Self.unavailable)
    }

    @objc func start(_ call: CAPPluginCall) {
        #if canImport(FamilyControls)
        if #available(iOS 16.0, *) {
            guard ShieldController.shared.authorized else {
                call.reject("Noch nicht freigegeben (Einstellungen → Fokus-Sperre).")
                return
            }
            ShieldController.shared.start()
            call.resolve()
            return
        }
        #endif
        call.reject(Self.unavailable)
    }

    @objc func stop(_ call: CAPPluginCall) {
        #if canImport(FamilyControls)
        if #available(iOS 16.0, *) {
            ShieldController.shared.stop()
            call.resolve()
            return
        }
        #endif
        call.reject(Self.unavailable)
    }
}

#if canImport(FamilyControls)
@available(iOS 16.0, *)
final class ShieldController {
    static let shared = ShieldController()
    private let store = ManagedSettingsStore()
    private let key = "tutor.focus.selection"

    var selection: FamilyActivitySelection {
        get {
            guard let data = UserDefaults.standard.data(forKey: key),
                  let value = try? JSONDecoder().decode(FamilyActivitySelection.self, from: data)
            else { return FamilyActivitySelection() }
            return value
        }
        set {
            if let data = try? JSONEncoder().encode(newValue) {
                UserDefaults.standard.set(data, forKey: key)
            }
        }
    }

    var hasSelection: Bool {
        let s = selection
        return !(s.applicationTokens.isEmpty && s.categoryTokens.isEmpty && s.webDomainTokens.isEmpty)
    }

    var authorized: Bool { AuthorizationCenter.shared.authorizationStatus == .approved }

    func authorize() async throws {
        try await AuthorizationCenter.shared.requestAuthorization(for: .individual)
    }

    func start() {
        let s = selection
        store.shield.applications = s.applicationTokens.isEmpty ? nil : s.applicationTokens
        store.shield.applicationCategories = s.categoryTokens.isEmpty ? nil : .specific(s.categoryTokens)
        store.shield.webDomains = s.webDomainTokens.isEmpty ? nil : s.webDomainTokens
    }

    func stop() {
        store.clearAllSettings()
    }
}

@available(iOS 16.0, *)
struct PickerView: View {
    @State var selection: FamilyActivitySelection
    let onDone: (FamilyActivitySelection) -> Void

    var body: some View {
        NavigationView {
            FamilyActivityPicker(selection: $selection)
                .navigationTitle("Ablenkungen wählen")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Fertig") { onDone(selection) }
                    }
                }
        }
        .navigationViewStyle(.stack)
    }
}
#endif
