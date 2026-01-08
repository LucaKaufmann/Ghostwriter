# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.kts.

# Keep Retrofit
-keepattributes Signature
-keepattributes Exceptions

# Keep Room entities
-keep class com.example.epilogue.data.local.** { *; }

# Keep Epublib
-dontwarn nl.siegmann.epublib.**
-keep class nl.siegmann.epublib.** { *; }
