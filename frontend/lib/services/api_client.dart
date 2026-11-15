import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

import '../config.dart';

/// Talks to our FastAPI backend.
/// Every request carries the user's Firebase login token, so the backend
/// knows who is asking.
class ApiClient {
  /// Never spin forever: after this the screen shows an error with "Try again".
  static const timeout = Duration(seconds: 60);

  Future<http.Response> _send(Future<http.Response> request) => request.timeout(
    timeout,
    onTimeout: () => throw Exception(
      'The server is taking too long. If it was just started, '
      'it may still be loading its AI models (up to a minute). Please try again.',
    ),
  );

  Future<Map<String, String>> _headers() async {
    final token = await FirebaseAuth.instance.currentUser?.getIdToken();
    return {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'};
  }

  Future<Map<String, dynamic>> get(String path) async {
    final res = await _send(http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers()));
    return _decode(res);
  }

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) async {
    final res = await _send(
      http.post(Uri.parse('$apiBaseUrl$path'), headers: await _headers(), body: jsonEncode(body)),
    );
    return _decode(res);
  }

  /// GET for endpoints that return a JSON list (e.g. /market/roles).
  Future<List<dynamic>> getList(String path) async {
    final res = await _send(http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers()));
    if (res.statusCode >= 400) _decode(res);
    return jsonDecode(res.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> put(String path, Map<String, dynamic> body) async {
    final res = await _send(http.put(Uri.parse('$apiBaseUrl$path'), headers: await _headers(), body: jsonEncode(body)));
    return _decode(res);
  }

  /// Raw bytes (e.g. the profile photo); null on 404.
  Future<List<int>?> getBytes(String path) async {
    final res = await _send(http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers()));
    if (res.statusCode == 404) return null;
    if (res.statusCode >= 400) _decode(res);
    return res.bodyBytes;
  }

  Future<Map<String, dynamic>> delete(String path) async {
    final res = await _send(http.delete(Uri.parse('$apiBaseUrl$path'), headers: await _headers()));
    return _decode(res);
  }

  /// Upload a file (e.g. a resume PDF) as multipart form data.
  Future<Map<String, dynamic>> uploadFile(String path, List<int> bytes, String filename) async {
    final req = http.MultipartRequest('POST', Uri.parse('$apiBaseUrl$path'));
    final token = await FirebaseAuth.instance.currentUser?.getIdToken();
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
    final streamed = await req.send().timeout(const Duration(seconds: 120));
    return _decode(await http.Response.fromStream(streamed));
  }

  /// GET that returns null on 404 (e.g. "no resume uploaded yet").
  Future<Map<String, dynamic>?> getOrNull(String path) async {
    final res = await _send(http.get(Uri.parse('$apiBaseUrl$path'), headers: await _headers()));
    if (res.statusCode == 404) return null;
    return _decode(res);
  }

  Map<String, dynamic> _decode(http.Response res) {
    final data = res.body.isEmpty ? <String, dynamic>{} : jsonDecode(res.body);
    if (res.statusCode >= 400) {
      final detail = data is Map ? data['detail'] : data;
      if (detail is Map) {
        // {"message": ..., "errors": {"field": "what is wrong"}} (e.g. the profile form)
        throw ApiException(
          res.statusCode,
          '${detail['message'] ?? 'Request failed'}',
          (detail['errors'] as Map?)?.map((k, v) => MapEntry('$k', '$v')) ?? const {},
        );
      }
      throw ApiException(res.statusCode, '$detail');
    }
    return data as Map<String, dynamic>;
  }
}

/// An error answer from the backend. [fieldErrors] says what is wrong with each form field.
class ApiException implements Exception {
  ApiException(this.statusCode, this.message, [this.fieldErrors = const {}]);
  final int statusCode;
  final String message;
  final Map<String, String> fieldErrors;

  // Older screens show '$e' and strip the "API error 404: " prefix, so keep that format.
  @override
  String toString() => 'API error $statusCode: $message';
}

final api = ApiClient();
