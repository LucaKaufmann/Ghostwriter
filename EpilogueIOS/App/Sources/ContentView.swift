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
        TabView {
            FeedListView()
                .tabItem {
                    Label("Feeds", systemImage: "list.bullet")
                }

            HistoryView()
                .tabItem {
                    Label("History", systemImage: "book")
                }

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gear")
                }
        }
    }
}

#Preview {
    ContentView()
}
