import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

import '../config.dart';

/// Talks to our FastAPI backend.
/// Every request carries the user's Firebase login token, so the backend
/// knows who is asking.
class ApiClient {
  Future<Map<String, String>> _headers() async {
    final token = await FirebaseAuth.instance.currentUser?.getIdToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  Future<Map<String, dynamic>> get(String path) async {
    final res = await http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers());
    return _decode(res);
  }

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) async {
    final res = await http.post(
      Uri.parse('$apiBaseUrl$path'),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    return _decode(res);
  }

  /// Upload a file (e.g. a resume PDF) as multipart form data.
  Future<Map<String, dynamic>> uploadFile(String path, List<int> bytes, String filename) async {
    final req = http.MultipartRequest('POST', Uri.parse('$apiBaseUrl$path'));
    final token = await FirebaseAuth.instance.currentUser?.getIdToken();
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await req.send();
    return _decode(await http.Response.fromStream(streamed));
  }

  /// GET that returns null on 404 (e.g. "no resume uploaded yet").
  Future<Map<String, dynamic>?> getOrNull(String path) async {
    final res = await http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers());
    if (res.statusCode == 404) return null;
    return _decode(res);
  }

  Map<String, dynamic> _decode(http.Response res) {
    final data = res.body.isEmpty ? <String, dynamic>{} : jsonDecode(res.body);
    if (res.statusCode >= 400) {
      throw Exception('API error ${res.statusCode}: ${data is Map ? data['detail'] : data}');
    }
    return data as Map<String, dynamic>;
  }
}

final api = ApiClient();
