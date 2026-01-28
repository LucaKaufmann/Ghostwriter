//
//  SyncStatusBanner.swift
//  Epilogue
//
//  Compact sync status indicator for navigation bar.
//

import SwiftUI

struct SyncStatusBanner: View {
    @ObservedObject var coordinator: GhostwriterSyncCoordinator

    var body: some View {
        if coordinator.isSyncing {
            ProgressView()
                .controlSize(.small)
        } else if coordinator.lastSyncError != nil {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(.orange)
        }
    }
}
