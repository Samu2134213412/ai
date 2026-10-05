import ReplayKit
import CoreImage
import UIKit

/// Broadcast-Upload-Extension: schreibt alle ~2 s ein verkleinertes Bild des Bildschirms
/// als JPEG in den App-Group-Container. Die Tutor-App holt es von dort ab.
/// (Extensions haben nur ~50 MB Speicher → klein skalieren, nichts sammeln.)
class SampleHandler: RPBroadcastSampleHandler {
    private let appGroup = "group.de.tutor.app"
    private let ciContext = CIContext()
    private var lastWrite = Date.distantPast
    private lazy var directory: URL? =
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)

    override func broadcastStarted(withSetupInfo setupInfo: [String: NSObject]?) {
        lastWrite = .distantPast
    }

    override func processSampleBuffer(_ sampleBuffer: CMSampleBuffer, with sampleBufferType: RPSampleBufferType) {
        guard sampleBufferType == .video,
              Date().timeIntervalSince(lastWrite) >= 2.0,
              let directory = directory,
              let pixels = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        lastWrite = Date()

        var image = CIImage(cvPixelBuffer: pixels)
        if let raw = CMGetAttachment(sampleBuffer, key: RPVideoSampleOrientationKey as CFString, attachmentModeOut: nil),
           let number = raw as? NSNumber,
           let orientation = CGImagePropertyOrientation(rawValue: number.uint32Value) {
            image = image.oriented(orientation)
        }
        let longest = max(image.extent.width, image.extent.height)
        if longest > 1800 {
            let scale = 1800 / longest
            image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        }
        guard let jpeg = ciContext.jpegRepresentation(
            of: image,
            colorSpace: CGColorSpaceCreateDeviceRGB(),
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.8]
        ) else { return }

        try? jpeg.write(to: directory.appendingPathComponent("frame.jpg"), options: .atomic)
        // Version = Sekunden seit 1970: steigt auch nach einem Neustart der Übertragung.
        let version = Int(Date().timeIntervalSince1970)
        try? String(version).write(to: directory.appendingPathComponent("frame.version"),
                                   atomically: true, encoding: .utf8)
    }
}
