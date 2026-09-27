GRADLE := ../gradlew
XCFRAMEWORK_DIR := ../shared/build/XCFrameworks/release/EpilogueShared.xcframework
SIMULATOR_DESTINATION ?= platform=iOS Simulator,name=iPhone 16 Pro Max,OS=18.6

.PHONY: setup generate build test clean xcframework screenshot

## Resolve packages and generate a fresh workspace after building the shared framework
setup: generate

## Build the KMP shared XCFramework
xcframework:
	@echo "Building EpilogueShared XCFramework..."
	$(GRADLE) -p .. :shared:assembleEpilogueSharedXCFramework --no-daemon
	@echo "XCFramework ready at $(XCFRAMEWORK_DIR)"

## Generate Xcode project via Tuist (requires XCFramework)
generate: xcframework
	tuist install
	tuist generate --no-open

## Build the freshly generated simulator app without signing
build: setup
	xcodebuild build -workspace Epilogue.xcworkspace -scheme Epilogue \
		-destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO

## Run unit tests on an installed iOS simulator runtime
test: setup
	xcodebuild test -workspace Epilogue.xcworkspace -scheme Epilogue-Workspace \
		-destination '$(SIMULATOR_DESTINATION)' \
		-skip-testing:EpilogueUITests CODE_SIGNING_ALLOWED=NO

## Capture App Store screenshots via UI tests across simulators
screenshot: setup
	./scripts/capture_screenshots.sh

## Clean XCFramework build artifacts
clean:
	rm -rf ../shared/build/XCFrameworks
	@echo "XCFramework artifacts cleaned"
