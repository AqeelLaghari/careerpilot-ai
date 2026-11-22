import 'dart:convert';

import 'package:http/http.dart' as http;

/// Where the FastAPI backend is running.
///
/// Laptop (default): http://127.0.0.1:8000. Android phone on the same Wi-Fi: pass the PC's address,
///   flutter run -d PHONE_ID --dart-define=API_URL=http://192.168.1.5:8000
///
/// Published builds (Day 29: the website on Firebase Hosting and the Android APK) are built with
/// API_URL = the Azure server AND CONFIG_URL = the website's config.json (frontend/web/config.json).
/// At startup they read "api_url" from that file, so the server can be switched (e.g. another
/// Azure account, or a laptop on defense day) by editing one file, without rebuilding the apps.
/// If the file can't be read, the built-in API_URL is used.
String apiBaseUrl = const String.fromEnvironment('API_URL', defaultValue: 'http://127.0.0.1:8000');

const String _configUrl = String.fromEnvironment('CONFIG_URL');

/// Reads the server address from [_configUrl] (published builds only; laptops skip this).
Future<void> loadServerConfig({http.Client? client}) async {
  if (_configUrl.isEmpty) return;
  final url = Uri.base.resolve(_configUrl); // "config.json" on the website, a full https:// URL in the APK
  final c = client ?? http.Client();
  try {
    final res = await c
        .get(url.replace(queryParameters: {'t': '${DateTime.now().millisecondsSinceEpoch}'})) // never cached
        .timeout(const Duration(seconds: 4));
    if (res.statusCode != 200) return;
    final value = (jsonDecode(res.body) as Map)['api_url'];
    final parsed = value is String ? serverUrlFrom(value) : null;
    if (parsed != null) apiBaseUrl = parsed;
  } catch (_) {
    // offline or a bad file: keep the built-in address
  } finally {
    if (client == null) c.close();
  }
}

/// A usable server address (http/https, no trailing slash), or null.
String? serverUrlFrom(String value) {
  final v = value.trim().replaceFirst(RegExp(r'/+$'), '');
  final uri = Uri.tryParse(v);
  if (uri == null || !(uri.scheme == 'https' || uri.scheme == 'http') || uri.host.isEmpty) return null;
  return v;
}

/// Email/password accounts created on or after this day must verify their email (Day 23).
/// Must match VERIFY_EMAIL_FROM in backend/app/config.py. Older test accounts keep working.
final DateTime verifyEmailFrom = DateTime.utc(2026, 11, 16);
