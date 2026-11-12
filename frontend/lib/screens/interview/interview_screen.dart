import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../career/career_screen.dart' show EmptyHint;
import 'answer_screen.dart';

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
            Text('Interview practice', style: Theme.of(context).textTheme.headlineSmall),
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
                Text('Answered (${(answer!['duration_sec'] as num).round()} s)',
                    style: const TextStyle(color: AppColors.good, fontSize: 12)),
              ]),
          ]),
          const SizedBox(height: 8),
          Text(q['question'] as String, style: const TextStyle(fontSize: 16)),
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('What a strong answer covers', style: TextStyle(fontSize: 13)),
              childrenPadding: const EdgeInsets.only(bottom: 8),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [
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
