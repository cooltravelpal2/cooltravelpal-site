import Foundation
import AppKit
import CoreGraphics
import CoreText
import ImageIO
import UniformTypeIdentifiers

// Apply the site's quiet TravelPal mark to an image.
// This intentionally preserves the photograph; it only resizes, composites the
// mark, and writes a web-sized JPEG.
guard CommandLine.arguments.count == 4 else {
    fputs("usage: watermark_media.swift input-image output.jpg mark.png\n", stderr)
    exit(2)
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2]) as CFURL
let markURL = URL(fileURLWithPath: CommandLine.arguments[3]) as CFURL

let sourceOptions: [CFString: Any] = [
    kCGImageSourceCreateThumbnailFromImageAlways: true,
    kCGImageSourceCreateThumbnailWithTransform: true,
    kCGImageSourceThumbnailMaxPixelSize: 1800
]
guard let source = CGImageSourceCreateWithURL(inputURL, nil),
      let sourceImage = CGImageSourceCreateThumbnailAtIndex(source, 0, sourceOptions as CFDictionary),
      let markSource = CGImageSourceCreateWithURL(markURL, nil),
      let markImage = CGImageSourceCreateImageAtIndex(markSource, 0, nil) else {
    fputs("could not decode input or mark\n", stderr)
    exit(1)
}

let width = sourceImage.width
let height = sourceImage.height
let colorSpace = CGColorSpaceCreateDeviceRGB()
guard let context = CGContext(data: nil,
                              width: width,
                              height: height,
                              bitsPerComponent: 8,
                              bytesPerRow: width * 4,
                              space: colorSpace,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
    fputs("could not create drawing context\n", stderr)
    exit(1)
}

context.interpolationQuality = .high
context.draw(sourceImage, in: CGRect(x: 0, y: 0, width: width, height: height))

// Keep the photograph and any signage readable. The mark sits in the
// top-left corner so it protects ownership without covering the story.
let minDimension = CGFloat(min(width, height))
let badgeSize = max(110, minDimension * 0.12)
let edgeInset = minDimension * 0.035
let badgeRect = CGRect(x: edgeInset,
                       y: CGFloat(height) - badgeSize - edgeInset,
                       width: badgeSize,
                       height: badgeSize)
let badgePath = CGPath(roundedRect: badgeRect,
                       cornerWidth: badgeSize * 0.18,
                       cornerHeight: badgeSize * 0.18,
                       transform: nil)
context.saveGState()
context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 0.11))
context.addPath(badgePath)
context.fillPath()

let iconScale = min((badgeSize * 0.70) / CGFloat(markImage.width),
                    (badgeSize * 0.70) / CGFloat(markImage.height))
let iconWidth = CGFloat(markImage.width) * iconScale
let iconHeight = CGFloat(markImage.height) * iconScale
let iconRect = CGRect(x: badgeRect.midX - iconWidth / 2,
                      y: badgeRect.midY - iconHeight / 2,
                      width: iconWidth,
                      height: iconHeight)
context.setAlpha(0.36)
context.draw(markImage, in: iconRect)
context.restoreGState()

// Keep a restrained wordmark at the lower-right edge as a second ownership cue.
let label = NSAttributedString(string: "TravelPal", attributes: [
    .font: NSFont.systemFont(ofSize: max(15, minDimension * 0.014), weight: .medium),
    .foregroundColor: NSColor.white.withAlphaComponent(0.30)
])
let line = CTLineCreateWithAttributedString(label)
let bounds = CTLineGetBoundsWithOptions(line, [])
context.saveGState()
context.setShadow(offset: CGSize(width: 0, height: -1), blur: 2,
                  color: CGColor(gray: 0, alpha: 0.22))
context.textPosition = CGPoint(x: CGFloat(width) - bounds.width - minDimension * 0.035,
                               y: minDimension * 0.035)
CTLineDraw(line, context)
context.restoreGState()

guard let output = CGImageDestinationCreateWithURL(outputURL, UTType.jpeg.identifier as CFString, 1, nil) else {
    fputs("could not create JPEG destination\n", stderr)
    exit(1)
}
CGImageDestinationAddImage(output, context.makeImage()!, [kCGImageDestinationLossyCompressionQuality: 0.88] as CFDictionary)
guard CGImageDestinationFinalize(output) else {
    fputs("could not write output\n", stderr)
    exit(1)
}
