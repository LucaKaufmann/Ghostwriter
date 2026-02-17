JAVA_HOME ?= /Applications/Android Studio.app/Contents/jbr/Contents/Home
GRADLE := JAVA_HOME="$(JAVA_HOME)" ../gradlew
XCFRAMEWORK_DIR := ../shared/build/XCFrameworks/debug/EpilogueShared.xcframework

.PHONY: setup generate build clean xcframework

## Default: build XCFramework + generate Xcode project
setup: xcframework generate

## Build the KMP shared XCFramework
xcframework:
	@echo "Building EpilogueShared XCFramework..."
	$(GRADLE) -p .. :shared:assembleEpilogueSharedXCFramework
	@echo "XCFramework ready at $(XCFRAMEWORK_DIR)"

## Generate Xcode project via Tuist (requires XCFramework)
generate: $(XCFRAMEWORK_DIR)
	tuist generate

## Build via Tuist CLI (requires XCFramework)
build: $(XCFRAMEWORK_DIR)
	tuist build

## Build XCFramework if missing
$(XCFRAMEWORK_DIR):
	$(MAKE) xcframework

## Clean XCFramework build artifacts
clean:
	rm -rf ../shared/build/XCFrameworks
	@echo "XCFramework artifacts cleaned"
