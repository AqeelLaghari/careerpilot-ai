import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';

/// The live connection to the Interview Coach for one session.
/// Text messages are JSON; audio goes as binary frames (PCM 16-bit, mono, 16 kHz).
class InterviewSocket {
  InterviewSocket(this.sessionId);
  final String sessionId;

  WebSocketChannel? _channel;
  final _messages = StreamController<Map<String, dynamic>>.broadcast();

  /// Every message from the server (ready, started, progress, saved, error...).
  Stream<Map<String, dynamic>> get messages => _messages.stream;

  Future<void> connect() async {
    final url = '${apiBaseUrl.replaceFirst(RegExp(r'^http'), 'ws')}/interview/ws';
    final channel = WebSocketChannel.connect(Uri.parse(url));
    _channel = channel;
    await channel.ready;
    channel.stream.listen(
      (data) {
        if (data is String) _messages.add(jsonDecode(data) as Map<String, dynamic>);
      },
      onDone: () => _messages.add({'type': 'closed', 'code': channel.closeCode}),
      onError: (Object e) => _messages.add({'type': 'closed', 'code': null, 'message': '$e'}),
    );
    // Browsers can't add a login header to a WebSocket, so the token is the first message.
    final token = await FirebaseAuth.instance.currentUser?.getIdToken();
    send({'type': 'auth', 'token': token ?? '', 'session_id': sessionId});
  }

  void send(Map<String, dynamic> msg) => _channel?.sink.add(jsonEncode(msg));

  void sendAudio(Uint8List chunk) => _channel?.sink.add(chunk);

  Future<void> close() async {
    await _channel?.sink.close();
    await _messages.close();
  }
}
