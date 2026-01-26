import ProjectDescription

let workspace = Workspace(
    name: "Epilogue",
    projects: [
        "App",
        "Modules/Domain",
        "Modules/Data"
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
