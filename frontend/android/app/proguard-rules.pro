# MediaPipe calls into these classes from native code, so the release build must not remove or rename them.
-keep class com.google.mediapipe.** { *; }
-keep class com.google.protobuf.** { *; }
# Flogger (Google's logging library inside MediaPipe) finds its caller by class name at run time;
# renamed classes crash the face model with "no caller found on the stack"
-keep class com.google.common.flogger.** { *; }
-dontwarn com.google.common.flogger.**
-dontwarn com.google.mediapipe.**
-dontwarn com.google.protobuf.**
-dontwarn javax.annotation.**
-dontwarn com.google.auto.value.**
# MediaPipe ships AutoValue's code generator (only used when compiling); its desktop-Java classes don't exist on Android
-dontwarn javax.lang.model.**
-dontwarn autovalue.shaded.**
