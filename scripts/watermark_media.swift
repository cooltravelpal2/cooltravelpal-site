import Foundation
import AppKit
import CoreGraphics
import CoreText
import ImageIO
import UniformTypeIdentifiers

// Apply the site's quiet, centered TravelPal mark to an already-exported image.
// This intentionally preserves the photograph; it only resizes, composites the
// mark, and writes a web-sized JPEG.
guard CommandLine.arguments.count == 4 else {
    fputs("usage: watermark_media.swift input.jpg output.jpg mark.png\n", stderr)
    exit(2)
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2]) as CFURL
let markURL = URL(fileURLWithPath: CommandLine.arguments[3]) as CFURL

guard let source = CGImageSourceCreateWithURL(inputURL, nil),
      let sourceImage = CGImageSourceCreateImageAtIndex(source, 0, nil),
      let markSource = CGImageSourceCreateWithURL(markURL, nil),
      let markImage = CGImageSourceCreateImageAtIndex(markSource, 0, nil) else {
    fputs("could not decode input or mark\n", stderr)
    exit(1)
}

let maxWidth: CGFloat = 1800
let sourceWidth = CGFloat(sourceImage.width)
let scale = min(1, maxWidth / sourceWidth)
let width = max(1, Int((sourceWidth * scale).rounded()))
let height = max(1, Int((CGFloat(sourceImage.height) * scale).rounded()))
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
context.saveGState()
context.translateBy(x: 0, y: CGFloat(height))
context.scaleBy(x: 1, y: -1)
context.draw(sourceImage, in: CGRect(x: 0, y: 0, width: width, height: height))
context.restoreGState()

// A small translucent badge in the center is visible enough to identify the
// owner while leaving the photograph and any signage readable.
let minDimension = CGFloat(min(width, height))
let badgeSize = max(150, minDimension * 0.22)
let badgeRect = CGRect(x: (CGFloat(width) - badgeSize) / 2,
                       y: (CGFloat(height) - badgeSize) / 2,
                       width: badgeSize,
                       height: badgeSize)
let badgePath = CGPath(roundedRect: badgeRect,
                       cornerWidth: badgeSize * 0.18,
                       cornerHeight: badgeSize * 0.18,
                       transform: nil)
context.saveGState()
context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 0.16))
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
context.setAlpha(0.50)
context.draw(markImage, in: iconRect)
context.restoreGState()

// Keep a restrained wordmark at the lower-right edge as a second ownership cue.
let label = NSAttributedString(string: "TravelPal", attributes: [
    .font: NSFont.systemFont(ofSize: max(15, minDimension * 0.014), weight: .medium),
    .foregroundColor: NSColor.white.withAlphaComponent(0.48)
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
