//
//  SettingsView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import Domain

struct SettingsView: View {
    @Environment(\.settingsRepository) private var settingsRepository
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator

    @State private var apiKey = ""
    @State private var scheduledHour = 6
    @State private var scheduleEnabled = true
    @State private var minWordCount = 300
    @State private var showNotifications = true

    var body: some View {
        NavigationStack {
            Form {
                // MARK: - Ghostwriter Sync
                Section {
                    NavigationLink {
                        GhostwriterSettingsView(settingsRepository: settingsRepository)
                            .environmentObject(ghostwriterCoordinator)
                    } label: {
                        HStack {
                            Label("Ghostwriter", systemImage: "cloud.fill")
                            Spacer()
                            if ghostwriterCoordinator.isSyncing {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else if ghostwriterCoordinator.lastSyncError != nil {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundColor(.orange)
                            }
                        }
                    }
                } footer: {
                    if let lastSync = ghostwriterCoordinator.lastSyncTime {
                        Text("Last sync: \(lastSync.formatted(date: .abbreviated, time: .shortened))")
                    }
                }

                Section("API Configuration") {
                    SecureField("OpenAI API Key", text: $apiKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section("Schedule") {
                    Toggle("Enable Scheduled Digests", isOn: $scheduleEnabled)
                    if scheduleEnabled {
                        Picker("Generation Time", selection: $scheduledHour) {
                            ForEach(0..<24) { hour in
                                Text("\(hour):00").tag(hour)
                            }
                        }
                    }
                }

                Section("Content Filters") {
                    Stepper("Min Word Count: \(minWordCount)", value: $minWordCount, in: 0...1000, step: 50)
                    Text("Articles shorter than this will be filtered out in Fidelity mode")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Notifications") {
                    Toggle("Show Digest Completion", isOn: $showNotifications)
                }

                Section {
                    Button("Generate Digest Now") {
                        // Manual trigger
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                }
            }
            .navigationTitle("Settings")
        }
    }
}
