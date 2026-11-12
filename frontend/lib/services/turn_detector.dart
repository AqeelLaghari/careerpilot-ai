/// Decides when the user has finished answering, from the microphone loudness:
/// they have spoken, and then stayed quiet for [silenceMs].
///
/// The background-noise level is learned while the user is quiet, so a fan or a noisy
/// room does not count as speech: speech = louder than max(minLevel, noise x noiseFactor).
class TurnDetector {
  TurnDetector({
    this.silenceMs = 3000,
    this.minSpeechMs = 600,
    this.noSpeechMs = 20000,
    this.minLevel = 0.06,
    this.noiseFactor = 2.5,
  });

  final int silenceMs; // quiet this long after speaking = end of the answer
  final int minSpeechMs; // this much speech before an answer can end (ignores a cough)
  final int noSpeechMs; // nothing said this long = "we can't hear you"
  final double minLevel;
  final double noiseFactor;

  double noise = 0.01;
  int spokenMs = 0;
  int quietMs = 0;
  int elapsedMs = 0;
  bool _ended = false;
  bool _warned = false;

  bool get hasSpoken => spokenMs >= minSpeechMs;
  double get threshold => noise * noiseFactor > minLevel ? noise * noiseFactor : minLevel;

  /// Feed one chunk: [level] 0..1 and its length in ms.
  /// Returns 'end' (answer finished), 'no_speech' (once), or null.
  String? feed(double level, int ms) {
    if (_ended) return null;
    elapsedMs += ms;
    if (level >= threshold) {
      spokenMs += ms;
      quietMs = 0;
    } else {
      quietMs += ms;
      noise = noise * 0.95 + level * 0.05; // learn the room's background noise
    }
    if (hasSpoken && quietMs >= silenceMs) {
      _ended = true;
      return 'end';
    }
    if (!hasSpoken && !_warned && elapsedMs >= noSpeechMs) {
      _warned = true;
      return 'no_speech';
    }
    return null;
  }

  void reset() {
    spokenMs = 0;
    quietMs = 0;
    elapsedMs = 0;
    _ended = false;
    _warned = false;
  }
}
