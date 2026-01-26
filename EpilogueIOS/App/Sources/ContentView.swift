//
//  ContentView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import Domain
import Data

struct ContentView: View {
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Image(systemName: "book.pages")
                    .font(.system(size: 80))
                    .foregroundStyle(.primary)

                Text("Hello Epilogue")
                    .font(.largeTitle)
                    .fontWeight(.bold)

                Text("iOS App - Phase 2 Complete")
                    .font(.title3)
                    .foregroundStyle(.secondary)

                Divider()
                    .padding(.vertical)

                VStack(alignment: .leading, spacing: 12) {
                    Label("Domain models created", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)

                    Label("Repository protocols defined", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)

                    Label("Tuist workspace configured", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)

                    Label("SwiftData persistence ready", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)

                    Label("Repository implementations done", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)

                    Label("Keychain integration complete", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                }
                .font(.body)
            }
            .padding()
            .navigationTitle("Epilogue")
        }
    }
}

#Preview {
    ContentView()
}
