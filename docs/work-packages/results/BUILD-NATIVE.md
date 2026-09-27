# BUILD-NATIVE result

Base: `e6e62677fe4f5b8f516e226a48080008cafc04e0` on `codex/build-native-baseline`. The final commit and pull request are recorded in the worker handoff.

## Change

- Native setup now builds the Kotlin `EpilogueShared` XCFramework before resolving Tuist packages and generating the Xcode workspace. `make build` and `make test` provide signing-free simulator commands.
- Tuist 4.152.0 and exact FeedKit 9.1.2, SwiftSoup 2.13.9, and ZIPFoundation 0.9.20 versions are documented and used for generation. The package versions match the locally resolved baseline.
- New native CI checks run Android/shared JVM tests and an iOS simulator build/unit suite on explicit hosted runners. Neither job loads provider keys or calls a real Ghostwriter service.
- Three baseline test prerequisites were fixed: Robolectric supplies Android XML serialization to the EPUB tests; an AIServices test now matches its non-Equatable error case; the Ghostwriter string initializer rejects relative or unsupported server URLs that `URL(string:)` otherwise accepts.

## Local evidence

- JDK 17.0.17, Android SDK platform 35 and build tools 34.0.0, Gradle wrapper 8.5, Tuist 4.152.0, Xcode 26.5 with iOS 18.6 simulator.
- `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon`: passed; 80 Android tests and 19 shared tests, no failures. See `native-tests-robolectric.log` and JUnit XML.
- `./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon`: passed; debug and release frameworks generated. See `native-xcframework.log`.
- `make -C EpilogueIOS setup`: passed; fresh Tuist generation included `URL+Validation.swift`. See `native-setup-final.log`.
- Signing-free iOS simulator app build: passed before the final fixture/URL check. See `native-sim-build.log`. The unit test command recompiles affected sources.
- `xcodebuildmcp simulator test` with scheme `Epilogue-Workspace`, iPhone 16 Pro Max (iOS 18.6), `CODE_SIGNING_ALLOWED=NO`, and `-skip-testing:EpilogueUITests`: passed, 70/70 tests. See `native-sim-tests-final.log`. The first full run exposed one invalid-URL baseline defect (69 passed, 1 failed), fixed and rerun.

## Limits

The macOS 15 ARM hosted runner's Xcode 26.3 and iPhone 16 Pro Max (iOS 18.6) installation are listed in the [published runner image inventory](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md). CI explicitly fails if that destination is absent. The first hosted run stopped in both jobs before any project build because the Android setup action requested a retired default `tools` package; the workflow now requests only `platform-tools`. This follow-up has not yet run on GitHub Actions. The repository has not been signed, distributed, or deployed. Baseline Swift warnings remain outside this build/test wiring package.
