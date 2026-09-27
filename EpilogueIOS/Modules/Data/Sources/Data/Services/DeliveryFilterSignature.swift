import Foundation
import CryptoKit

public enum DeliveryFilterSignature {
    public static func make(minWordCount: Int) -> String {
        let revision = "ios-content-filter-v1:min-words=\(minWordCount)"
        return SHA256.hash(data: Data(revision.utf8))
            .map { String(format: "%02x", $0) }.joined()
    }
}
