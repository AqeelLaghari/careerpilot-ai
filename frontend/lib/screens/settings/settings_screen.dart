import 'package:flutter/material.dart';

import '../../services/profile_store.dart';
import '../../services/speaker.dart';
import '../../theme.dart';

/// Settings (Day 24): appearance, the interviewer's voice and the interview language.
/// Saved in the user's account, so they apply on every device they log in from.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  Speaker? _sample;
  bool _playing = false;
  String? _voiceNote; // which voice the sample used

  @override
  void dispose() {
    _sample?.stop();
    super.dispose();
  }

  Future<void> _set(String name, String value) async {
    try {
      await profileStore.saveSetting(name, value);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not save the setting. Check your connection and try again.')),
        );
      }
    }
  }

  Future<void> _playSample() async {
    await _sample?.stop();
    final voice = _sample = Speaker(); // a new speaker picks up the current voice settings
    setState(() => _playing = true);
    final mode = await voice.ready();
    if (mounted) setState(() => _voiceNote = _describe(mode, voice.voiceName));
    final name = profileStore.firstName;
    if (voice.language == 'ur') {
      await voice.sayLine(
        'السلام علیکم $name، میں آپ کا CareerPilot انٹرویوور ہوں۔ کسی ایسے پروجیکٹ کے بارے میں بتائیں جس پر آپ کو فخر ہو۔',
        hindi:
            'अस्सलाम ओ अलैकुम $name, मैं आपका CareerPilot इंटरव्यूअर हूँ। किसी ऐसे प्रोजेक्ट के बारे में बताइए जिस पर आपको फ़ख़्र हो।',
      );
    } else {
      await voice.say(
        'Hi $name, I am your CareerPilot interviewer. '
        'Tell me about a project you are proud of.',
      );
    }
    if (mounted && identical(_sample, voice)) setState(() => _playing = false);
  }

  static String _describe(String mode, String? name) => switch (mode) {
    'ur' => 'Urdu voice: $name',
    'hi' =>
      'No Urdu voice in this browser, so a Hindi voice reads Urdu: $name. Microsoft Edge or Android has a real Urdu voice.',
    'none' => 'No Urdu or Hindi voice in this browser: Urdu questions will be shown as text only.',
    _ => 'Voice: ${name ?? 'browser default'}',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListenableBuilder(
        listenable: profileStore,
        builder: (context, _) => Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 40),
              children: [
                _Section(
                  icon: Icons.palette_outlined,
                  title: 'Appearance',
                  subtitle: '"System" follows your computer or phone\'s own light/dark setting.',
                  child: _Choice(
                    value: profileStore.setting('theme'),
                    options: const {
                      'system': ('System', Icons.brightness_auto_outlined),
                      'light': ('Light', Icons.light_mode_outlined),
                      'dark': ('Dark', Icons.dark_mode_outlined),
                    },
                    onChanged: (v) => _set('theme', v),
                  ),
                ),
                _Section(
                  icon: Icons.record_voice_over_outlined,
                  title: 'Interviewer voice',
                  subtitle:
                      'Uses the free voices built into your browser or phone, so the exact voice '
                      'depends on your device.',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _Label('Voice'),
                      _Choice(
                        value: profileStore.setting('voice'),
                        options: const {
                          'female': ('Female', Icons.face_3_outlined),
                          'male': ('Male', Icons.face_outlined),
                        },
                        onChanged: (v) => _set('voice', v),
                      ),
                      const SizedBox(height: 16),
                      _Label('Speaking speed'),
                      _Choice(
                        value: profileStore.setting('speech_rate'),
                        options: const {
                          'slow': ('Slower', Icons.slow_motion_video_outlined),
                          'normal': ('Normal', Icons.play_circle_outline),
                          'fast': ('Faster', Icons.fast_forward_outlined),
                        },
                        onChanged: (v) => _set('speech_rate', v),
                      ),
                      const SizedBox(height: 16),
                      OutlinedButton.icon(
                        onPressed: _playing
                            ? () {
                                _sample?.stop();
                                setState(() => _playing = false);
                              }
                            : _playSample,
                        icon: Icon(_playing ? Icons.stop_circle_outlined : Icons.volume_up_outlined),
                        label: Text(_playing ? 'Stop' : 'Play a sample'),
                      ),
                      if (_voiceNote != null) ...[
                        const SizedBox(height: 8),
                        Text(_voiceNote!, style: TextStyle(color: AppColors.textMuted, fontSize: 12.5, height: 1.4)),
                      ],
                    ],
                  ),
                ),
                _Section(
                  icon: Icons.translate_outlined,
                  title: 'Interview language',
                  subtitle:
                      'The language of the live video interview: what the interviewer speaks and understands, '
                      'and the language of your report.',
                  child: Column(
                    children: [
                      RadioGroup<String>(
                        groupValue: profileStore.setting('language'),
                        onChanged: (v) {
                          if (v == null) return;
                          setState(() => _voiceNote = null);
                          _set('language', v);
                        },
                        child: Column(
                          children: [
                            const RadioListTile(value: 'en', title: Text('English'), contentPadding: EdgeInsets.zero),
                            RadioListTile(
                              value: 'ur',
                              contentPadding: EdgeInsets.zero,
                              title: Row(children: [const Text('اردو  Urdu'), const SizedBox(width: 10), _Tag('New')]),
                              subtitle: const Text(
                                'Questions in Urdu with Roman Urdu subtitles. Answer in Urdu or mixed Urdu-English; '
                                'the report is in Roman Urdu. Press "Play a sample" to check the voice.',
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.cloud_done_outlined, size: 16, color: AppColors.textFaint),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Settings are saved to your account and apply on every device.',
                        style: TextStyle(color: AppColors.textMuted, fontSize: 12.5),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.icon, required this.title, required this.subtitle, required this.child});
  final IconData icon;
  final String title, subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 16),
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.brand, size: 22),
              const SizedBox(width: 10),
              Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 4),
          Text(subtitle, style: TextStyle(color: AppColors.textMuted, fontSize: 13, height: 1.4)),
          const SizedBox(height: 16),
          child,
        ],
      ),
    ),
  );
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Text(
      text,
      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.textMuted),
    ),
  );
}

class _Tag extends StatelessWidget {
  const _Tag(this.text);
  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
    decoration: BoxDecoration(color: AppColors.brandTint, borderRadius: BorderRadius.circular(20)),
    child: Text(
      text,
      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.brand),
    ),
  );
}

/// A row of segmented choices.
class _Choice extends StatelessWidget {
  const _Choice({required this.value, required this.options, required this.onChanged});
  final String value;
  final Map<String, (String, IconData)> options;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) => SegmentedButton<String>(
    showSelectedIcon: false,
    segments: [
      for (final e in options.entries)
        ButtonSegment(value: e.key, label: Text(e.value.$1), icon: Icon(e.value.$2, size: 18)),
    ],
    selected: {value},
    onSelectionChanged: (s) => onChanged(s.first),
  );
}
