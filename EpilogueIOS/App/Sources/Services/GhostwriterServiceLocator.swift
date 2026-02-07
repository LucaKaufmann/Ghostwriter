//
//  GhostwriterServiceLocator.swift
//  Epilogue
//
//  Created on 2026-02-07.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Simple service locator so app delegate callbacks can trigger sync.
@MainActor
final class GhostwriterServiceLocator {
    static let shared = GhostwriterServiceLocator()

    var coordinator: GhostwriterSyncCoordinator?
}

