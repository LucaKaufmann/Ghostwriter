//
//  HistoryView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import SwiftData
import Domain

struct HistoryView: View {
    @Query(sort: \Digest.generatedAt, order: .reverse) private var digests: [Digest]

    var body: some View {
        NavigationStack {
            List {
                ForEach(digests) { digest in
                    DigestRow(digest: digest)
                }
            }
            .navigationTitle("History")
        }
    }
}

struct DigestRow: View {
    let digest: Digest

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(digest.generatedAt, style: .date)
                .font(.headline)
            HStack {
                Label("\(digest.articleCount) articles", systemImage: "doc.text")
                    .font(.caption)
                Spacer()
                Text(digest.triggerType.displayName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let error = digest.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            } else if digest.isComplete {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("Complete")
                }
                .font(.caption)
            }
        }
        .padding(.vertical, 4)
    }
}
