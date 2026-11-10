import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';

/// Admin only: the skills the app learned by itself from job postings.
/// Remove a wrong one (it is never learned again) or approve one that waits for review.
class LearnedSkillsScreen extends StatefulWidget {
  const LearnedSkillsScreen({super.key});

  @override
  State<LearnedSkillsScreen> createState() => _LearnedSkillsScreenState();
}

class _LearnedSkillsScreenState extends State<LearnedSkillsScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  String _filter = 'approved';

  static const _categories = [
    'programming_languages', 'web_frontend', 'web_backend', 'mobile', 'databases', 'cloud', 'devops',
    'data_science_ml', 'ai_llm', 'data_analytics_bi', 'testing_qa', 'security', 'networking_systems',
    'embedded_iot', 'blockchain_gamedev', 'design_ux', 'project_management', 'business_office',
    'soft_skills', 'marketing_sales', 'finance_accounting', 'human_resources', 'healthcare',
    'engineering_core', 'education_teaching', 'legal_admin',
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  String _msg(Object e) => '$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), '');

  void _toast(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _load() async {
    try {
      final d = await api.get('/market/learned');
      if (mounted) {
        setState(() {
          _data = d;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = _msg(e));
    }
  }

  Future<void> _set(String name, String status, [String? category]) async {
    try {
      await api.post('/market/learned/${Uri.encodeComponent(name)}',
          {'status': status, 'category': ?category});
      await _load();
      _toast(status == 'removed' ? '"$name" removed. It will not be learned again.' : '"$name" approved.');
    } catch (e) {
      _toast(_msg(e));
    }
  }

  Future<void> _approve(Map<String, dynamic> s) async {
    var cat = _categories.contains(s['category']) ? s['category'] as String : _categories.first;
    final picked = await showDialog<String>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setD) => AlertDialog(
          title: Text('Approve "${s['name']}"'),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Which group does this skill belong to?'),
            DropdownButton<String>(
              value: cat,
              isExpanded: true,
              items: [for (final c in _categories) DropdownMenuItem(value: c, child: Text(c))],
              onChanged: (v) => setD(() => cat = v!),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, cat), child: const Text('Approve')),
          ],
        ),
      ),
    );
    if (picked != null) await _set(s['name'] as String, 'approved', picked);
  }

  Future<void> _runNow() async {
    try {
      await api.post('/market/learn', {});
      _toast('Learning started. It takes a minute or two; pull down to refresh.');
    } catch (e) {
      _toast(_msg(e));
    }
  }

  String _lastRun(Map<String, dynamic> d) {
    if (d['last_run'] == null) return 'Not run yet.';
    final r = (d['report'] as Map?) ?? {};
    final when = DateTime.fromMillisecondsSinceEpoch(((d['last_run'] as num) * 1000).round());
    return [
      'Last run: ${when.toString().substring(0, 16)}${d['running'] == true ? ' (running now)' : ''}',
      '${r['postings'] ?? 0} postings',
      '${r['candidates'] ?? 0} candidates',
      'Gemini ${r['gemini'] == true ? 'checked them' : 'unavailable'}',
    ].join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final d = _data;
    Widget body;
    if (_error != null) {
      body = Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_error!)));
    } else if (d == null) {
      body = const Center(child: CircularProgressIndicator());
    } else {
      final skills = (d['skills'] as List).cast<Map<String, dynamic>>();
      final shown = skills.where((s) => s['status'] == _filter).toList();
      body = RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          Text(_lastRun(d), style: const TextStyle(color: Colors.grey)),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            segments: [
              for (final f in ['approved', 'pending', 'removed'])
                ButtonSegment(value: f, label: Text('$f (${skills.where((s) => s['status'] == f).length})')),
            ],
            selected: {_filter},
            onSelectionChanged: (v) => setState(() => _filter = v.first),
          ),
          const SizedBox(height: 8),
          if (shown.isEmpty) const Padding(padding: EdgeInsets.all(24), child: Center(child: Text('Nothing here.'))),
          for (final s in shown)
            Card(
              child: ListTile(
                title: Text(s['name'] as String),
                subtitle: Text([
                  s['category'] ?? 'no group yet',
                  '${s['postings']} postings',
                  if ((s['aliases'] as List? ?? []).isNotEmpty) 'also written: ${(s['aliases'] as List).join(', ')}',
                  'by ${s['by']}',
                ].join(' · ')),
                trailing: Wrap(children: [
                  if (s['status'] != 'approved')
                    IconButton(
                      tooltip: 'Approve',
                      icon: const Icon(Icons.check, color: AppColors.good),
                      onPressed: () => _approve(s),
                    ),
                  if (s['status'] != 'removed')
                    IconButton(
                      tooltip: 'Remove (never learn again)',
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => _set(s['name'] as String, 'removed'),
                    ),
                ]),
              ),
            ),
        ]),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Learned skills'), actions: [
        IconButton(tooltip: 'Run learning now', icon: const Icon(Icons.play_arrow), onPressed: _runNow),
      ]),
      body: body,
    );
  }
}
