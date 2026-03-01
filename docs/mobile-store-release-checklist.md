# Mobile Store Release Checklist

This document captures the executable release workflow for both mobile apps.

## 1. Preflight

1. Sync and branch:
   - `git checkout main`
   - `git pull --ff-only origin main`
   - `git checkout -b codex/release-mobile-store-YYYYMMDD`
2. Verify tools:
   - `xcodebuild -version`
   - `tuist version`
   - `asc --version`
   - `java -version` (or use Android Studio JBR via `JAVA_HOME`)
3. Verify ASC auth:
   - `asc auth status`
4. Resolve App Store app/build IDs:
   - `asc apps list --bundle-id com.codable.epilogue --output table`
   - If this returns empty, check existing listing(s): `asc apps list --output table`

## 2. Versioning

### Android

- `app/build.gradle.kts` reads release version values from:
  - `EPILOGUE_VERSION_CODE` (required integer for release tasks)
  - `EPILOGUE_VERSION_NAME` (defaults to `1.0.0`)
- Example:
  - `EPILOGUE_VERSION_CODE=42 EPILOGUE_VERSION_NAME=1.0.0 ./gradlew :app:bundleRelease`

### iOS

- `EpilogueIOS/App/Project.swift` reads:
  - `EPILOGUE_IOS_MARKETING_VERSION` (defaults to `1.0.0`)
  - `EPILOGUE_IOS_BUILD_NUMBER` (defaults to `1`)
- Example:
  - `EPILOGUE_IOS_MARKETING_VERSION=1.0.0 EPILOGUE_IOS_BUILD_NUMBER=42 tuist generate`

## 3. Android Build + Upload

1. Create `keystore.properties` from `keystore.properties.example`.
2. Build release bundle:
   - `JAVA_HOME=\"/Applications/Android Studio.app/Contents/jbr/Contents/Home\" ./gradlew clean :shared:assembleEpilogueSharedXCFramework :app:test :app:lintRelease :app:bundleRelease`
3. Upload `.aab` (`app/build/outputs/bundle/release/`) to Play Console Internal Testing.
4. Validate Play pre-launch report and policy status before production rollout.

## 4. iOS Build + Upload (ASC CLI)

1. Generate workspace/project:
   - `cd EpilogueIOS && tuist install && tuist generate`
2. Archive:
   - `xcodebuild clean archive -workspace Epilogue.xcworkspace -scheme Epilogue -configuration Release -destination \"generic/platform=iOS\" -archivePath build/Epilogue.xcarchive`
3. Export IPA:
   - `xcodebuild -exportArchive -archivePath build/Epilogue.xcarchive -exportPath build/export -exportOptionsPlist ExportOptions-AppStore.plist`
4. Upload TestFlight:
   - `asc publish testflight --app <APP_ID> --ipa build/export/Epilogue.ipa --group <GROUP_ID> --wait --notify`
5. Submit App Store after beta validation:
   - `asc publish appstore --app <APP_ID> --ipa build/export/Epilogue.ipa --version 1.0.0 --wait --submit --confirm`

## 5. Store Metadata + Compliance

### App Store Connect

1. Age rating questionnaire completed.
2. Privacy policy + support URL set.
3. Localization fields complete for target locales.
4. Required screenshots uploaded.
5. Export compliance resolved (`ITSAppUsesNonExemptEncryption` is configured).

### Google Play Console

1. App content forms complete:
   - Data safety
   - Ads declaration
   - Content rating
   - App access (if required)
   - Target audience/news declarations (if applicable)
2. Listing assets complete:
   - App icon
   - Feature graphic
   - Screenshots by device class
3. Internal/beta testing sign-off complete before production rollout.
