import ProjectDescription

let workspace = Workspace(
    name: "Epilogue",
    projects: [
        "App",
        "Modules/Domain",
        "Modules/Data",
        "Modules/GhostwriterClient",
        "Modules/ContentProcessing",
        "Modules/AIServices",
        "Modules/EPUBGeneration"
    ],
    fileHeaderTemplate: .string(
        """
        //
        //  __FILENAME__
        //  Epilogue
        //
        //  Created on __DATE__.
        //  Copyright © 2026 Epilogue. All rights reserved.
        //
        """
    )
)
