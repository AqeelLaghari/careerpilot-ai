/// Where the FastAPI backend is running.
///
/// Web (same computer): http://127.0.0.1:8000 (the default).
/// Android phone: the phone can't reach "127.0.0.1" of your PC, so pass the PC's
/// Wi-Fi address when running:
///   flutter run -d PHONE_ID --dart-define=API_URL=http://192.168.1.5:8000
/// We point this at the deployed backend on Day 25.
const String apiBaseUrl = String.fromEnvironment('API_URL', defaultValue: 'http://127.0.0.1:8000');
