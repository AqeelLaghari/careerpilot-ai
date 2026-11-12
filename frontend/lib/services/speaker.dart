import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// The interviewer's voice: the free text-to-speech built into the browser (web) or the
/// phone (Android). No internet service, no cost.
class Speaker {
  final _tts = FlutterTts();
  bool _ready = false;
  String? voiceName;

  Future<void> _init() async {
    if (_ready) return;
    _ready = true;
    await _tts.awaitSpeakCompletion(true); // speak() returns when the sentence is finished
    await _tts.setLanguage('en-US');
    // "Normal" speed is 1.0 in browsers but 0.5 on Android
    await _tts.setSpeechRate(kIsWeb ? 0.95 : 0.5);
    await _tts.setPitch(1.0);
    try {
      final voices = ((await _tts.getVoices) as List?)?.cast<Map>() ?? [];
      final english = voices.where((v) => '${v['locale']}'.toLowerCase().startsWith('en')).toList();
      // Clearer voices first: Windows/Edge "Natural" voices and Chrome's "Google" voices
      int rank(Map v) {
        final n = '${v['name']}'.toLowerCase();
        if (n.contains('natural')) return 0;
        if (n.contains('google') && n.contains('us')) return 1;
        if (n.contains('google')) return 2;
        if ('${v['locale']}'.toLowerCase() == 'en-us') return 3;
        return 4;
      }

      english.sort((a, b) => rank(a).compareTo(rank(b)));
      if (english.isNotEmpty) {
        final v = english.first;
        voiceName = '${v['name']}';
        await _tts.setVoice({'name': '${v['name']}', 'locale': '${v['locale']}'});
      }
    } catch (_) {
      // keep the default voice
    }
  }

  /// Say [text]; the Future completes when it has been spoken (or stopped).
  Future<void> say(String text) async {
    await _init();
    await _tts.stop();
    await _tts.speak(text);
  }

  Future<void> stop() => _tts.stop();
}
