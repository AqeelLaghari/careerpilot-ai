import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../career/career_screen.dart' show EmptyHint;
import 'answer_screen.dart';
import 'camera_check_screen.dart';
import 'live_interview_screen.dart';
import 'speech_report.dart';

/// Interview Coach: practice questions made for this user's CV and target role.
/// (Answering by voice and camera, with scores, is added on top of this screen later.)
class InterviewScreen extends StatefulWidget {
  const InterviewScreen({super.key});

  @override
  State<InterviewScreen> createState() => _InterviewScreenState();
}

class _InterviewScreenState extends State<InterviewScreen> {
  List<Map<String, dynamic>> _sessions = [];
  Map<String, dynamic>? _session;
  bool _loading = true;
  bool _generating = false;
  bool _noResume = false;
  String? _error;
  int _count = 8;
  int _minutes = 10; // live interview length

  @override
  void initState() {
    super.initState();
    _loadSessions();
  }

  String _msg(Object e) => '$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), '');

  Future<void> _loadSessions() async {
    try {
      final list = (await api.getList('/interview/sessions')).cast<Map<String, dynamic>>();
      Map<String, dynamic>? latest;
      if (list.isNotEmpty) latest = await api.get('/interview/sessions/${list.first['id']}');
      if (!mounted) return;
      setState(() {
        _sessions = list;
        _session = latest;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = _msg(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generate() async {
    setState(() {
      _generating = true;
      _error = null;
    });
    try {
      final s = await api.post('/interview/sessions', {'count': _count});
      if (!mounted) return;
      setState(() {
        _session = s;
        _sessions = [
          {'id': s['id'], 'created_at': s['created_at'], 'role': s['role'], 'questions': (s['questions'] as List).length},
          ..._sessions,
        ];
      });
    } catch (e) {
      if (!mounted) return;
      final msg = _msg(e);
      setState(() => msg.toLowerCase().contains('upload a resume') ? _noResume = true : _error = msg);
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _open(String id) async {
    try {
      final s = await api.get('/interview/sessions/$id');
      if (mounted) setState(() => _session = s);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_msg(e))));
    }
  }

  /// The main feature: a live video interview with a spoken, adaptive interviewer.
  Widget _liveCard() => Card(
        color: AppColors.brand.withValues(alpha: 0.06),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Icon(Icons.video_call, color: AppColors.brand, size: 28),
              const SizedBox(width: 8),
              Text('Live video interview', style: Theme.of(context).textTheme.titleLarge),
            ]),
            const SizedBox(height: 6),
            const Text('A real conversation: the interviewer speaks, listens to your answers and asks '
                'follow-up questions, from your background to technical topics. Camera on, like a video call.'),
            const SizedBox(height: 12),
            Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              SegmentedButton<int>(
                segments: const [
                  ButtonSegment(value: 5, label: Text('5 min')),
                  ButtonSegment(value: 10, label: Text('10 min')),
                  ButtonSegment(value: 15, label: Text('15 min')),
                ],
                selected: {_minutes},
                onSelectionChanged: (v) => setState(() => _minutes = v.first),
              ),
              FilledButton.icon(
                onPressed: () async {
                  await Navigator.of(context)
                      .push(MaterialPageRoute(builder: (_) => LiveInterviewScreen(minutes: _minutes)));
                  _loadSessions();
                },
                icon: const Icon(Icons.play_arrow),
                label: const Text('Start interview'),
              ),
            ]),
          ]),
        ),
      );

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_noResume) {
      return const EmptyHint(
        icon: Icons.upload_file,
        title: 'Upload your resume first',
        text: 'Interview questions are made from your CV and your target role.',
      );
    }
    final s = _session;
    return ListView(padding: const EdgeInsets.all(16), children: [
      Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 900),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _liveCard(),
            const SizedBox(height: 24),
            Text('Practice question sets', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            const Text('Questions made for your CV, your skills and your target role. A new set every time.',
                style: TextStyle(color: Colors.grey)),
            const SizedBox(height: 12),
            Wrap(spacing: 12, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              SegmentedButton<int>(
                segments: const [
                  ButtonSegment(value: 5, label: Text('5 questions')),
                  ButtonSegment(value: 8, label: Text('8')),
                  ButtonSegment(value: 10, label: Text('10')),
                ],
                selected: {_count},
                onSelectionChanged: _generating ? null : (v) => setState(() => _count = v.first),
              ),
              FilledButton.icon(
                onPressed: _generating ? null : _generate,
                icon: _generating
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.auto_awesome),
                label: Text(_generating ? 'Preparing questions…' : 'New interview'),
              ),
              OutlinedButton.icon(
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => const CameraCheckScreen())),
                icon: const Icon(Icons.videocam_outlined),
                label: const Text('Camera check'),
              ),
              if (_sessions.length > 1)
                PopupMenuButton<String>(
                  tooltip: 'Earlier sets',
                  onSelected: _open,
                  itemBuilder: (_) => [
                    for (final x in _sessions)
                      PopupMenuItem(
                        value: x['id'] as String,
                        child: Text('${_date(x['created_at'] as num)} · ${x['role']} · ${x['questions']} questions'),
                      ),
                  ],
                  child: const Padding(
                    padding: EdgeInsets.all(8),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.history, size: 18),
                      SizedBox(width: 4),
                      Text('Earlier sets'),
                    ]),
                  ),
                ),
            ]),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: const TextStyle(color: AppColors.bad)),
              ),
            const SizedBox(height: 16),
            if (s == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(child: Text('Press "New interview" to get your first set of questions.')),
              )
            else ...[
              Text('${s['role']} · ${s['level']} level · ${(s['questions'] as List).length} questions',
                  style: Theme.of(context).textTheme.titleMedium),
              Text('Made ${_date(s['created_at'] as num)}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: () async {
                  await Navigator.of(context).push(MaterialPageRoute(builder: (_) => AnswerScreen(session: s)));
                  _open(s['id'] as String); // show which questions are answered now
                },
                icon: const Icon(Icons.mic),
                label: Text((s['answers'] as Map?)?.isNotEmpty == true ? 'Continue answering' : 'Answer out loud'),
              ),
              const SizedBox(height: 8),
              for (final (i, q) in (s['questions'] as List).cast<Map<String, dynamic>>().indexed)
                _QuestionCard(number: i + 1, q: q, answer: (s['answers'] as Map?)?[q['id']] as Map?),
            ],
          ]),
        ),
      ),
    ]);
  }
}

String _date(num epochSeconds) {
  final d = DateTime.fromMillisecondsSinceEpoch((epochSeconds * 1000).round());
  return '${d.day}/${d.month}/${d.year} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}

class _QuestionCard extends StatelessWidget {
  const _QuestionCard({required this.number, required this.q, this.answer});
  final int number;
  final Map<String, dynamic> q;
  final Map? answer; // set once the question was answered out loud

  static const _labels = {
    'intro': ('Introduction', Icons.waving_hand_outlined),
    'technical': ('Skill', Icons.build_outlined),
    'project': ('Your project', Icons.folder_open),
    'gap': ('Skill to learn', Icons.trending_up),
    'behavioural': ('Behaviour (STAR)', Icons.groups_outlined),
    'situational': ('Situation', Icons.lightbulb_outline),
  };

  @override
  Widget build(BuildContext context) {
    final (label, icon) = _labels[q['type']] ?? ('Question', Icons.help_outline);
    final about = q['skill'] ?? q['project'];
    final minutes = ((q['time_limit_sec'] as num) / 60).toStringAsFixed(1).replaceAll('.0', '');
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
            CircleAvatar(radius: 12, child: Text('$number', style: const TextStyle(fontSize: 12))),
            Chip(
              avatar: Icon(icon, size: 16),
              label: Text(about == null ? label : '$label: $about', style: const TextStyle(fontSize: 12)),
              visualDensity: VisualDensity.compact,
            ),
            Text('about $minutes min', style: const TextStyle(color: Colors.grey, fontSize: 12)),
            if (answer != null)
              Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.check_circle, size: 16, color: AppColors.good),
                const SizedBox(width: 4),
                Text(
                    answer!['metrics'] == null
                        ? 'Answered (${(answer!['duration_sec'] as num).round()} s)'
                        : 'Answered · ${answer!['metrics']['wpm']} words/min · ${answer!['metrics']['filler_count']} fillers',
                    style: const TextStyle(color: AppColors.good, fontSize: 12)),
              ]),
          ]),
          const SizedBox(height: 8),
          Text(q['question'] as String, style: const TextStyle(fontSize: 16)),
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text(answer?['transcript'] != null ? 'Your answer and what a strong answer covers'
                  : 'What a strong answer covers', style: const TextStyle(fontSize: 13)),
              childrenPadding: const EdgeInsets.only(bottom: 8),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (answer?['transcript'] != null) ...[
                  SpeechReport(
                    transcript: answer!['transcript'] as String,
                    metrics: (answer!['metrics'] as Map).cast<String, dynamic>(),
                    vision: (answer!['vision'] as Map?)?.cast<String, dynamic>(),
                  ),
                  const Divider(height: 24),
                  const Text('What a strong answer covers', style: TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                ],
                for (final k in (q['key_points'] as List).cast<String>())
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Icon(Icons.check, size: 16, color: AppColors.good),
                      const SizedBox(width: 6),
                      Expanded(child: Text(k)),
                    ]),
                  ),
              ],
            ),
          ),
        ]),
      ),
    );
  }
}
