import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../resume/resume_widgets.dart';

/// Interactive learning roadmap: tick tasks week by week.
/// Finishing every task of a skill marks the skill as learned (the backend adds it
/// to your profile, so your role match goes up and re-plans skip it).
class RoadmapScreen extends StatefulWidget {
  const RoadmapScreen({super.key, required this.initial});
  final Map<String, dynamic> initial;

  @override
  State<RoadmapScreen> createState() => _RoadmapScreenState();
}

class _RoadmapScreenState extends State<RoadmapScreen> {
  late Map<String, dynamic> _plan = widget.initial;
  final Set<String> _saving = {};
  bool _replanning = false;
  bool _changed = false;

  List<Map<String, dynamic>> get _weeks => (_plan['weeks'] as List).cast<Map<String, dynamic>>();
  List<Map<String, dynamic>> get _skills => (_plan['skills'] as List).cast<Map<String, dynamic>>();
  Map<String, dynamic> get _progress => _plan['progress'] as Map<String, dynamic>;
  Set<String> get _completed =>
      ((_plan['completed_skills'] as List?) ?? []).map((c) => (c as Map)['name'] as String).toSet();

  void _snack(String msg) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  Future<void> _toggle(Map<String, dynamic> task, bool done) async {
    final id = task['id'] as String;
    setState(() {
      task['done'] = done; // show the tick immediately; undo if the save fails
      _saving.add(id);
    });
    try {
      final r = await api.post('/roadmap/tasks/${Uri.encodeComponent(id)}', {'done': done});
      _changed = true;
      setState(() => _plan = r);
      final skill = r['skill_completed'];
      if (skill != null) {
        final mc = r['match_change'] as Map<String, dynamic>?;
        _celebrate(skill as String, mc);
      }
    } catch (e) {
      setState(() => task['done'] = !done);
      _snack('$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _saving.remove(id));
    }
  }

  void _celebrate(String skill, Map<String, dynamic>? mc) => showDialog(
        context: context,
        builder: (_) => AlertDialog(
          icon: const Icon(Icons.emoji_events, color: AppColors.warn, size: 48),
          title: Text('$skill learned!'),
          content: Text(mc == null
              ? '$skill is now part of your profile.'
              : '$skill is now part of your profile.\n\n'
                  'Your ${mc['role']} match: ${mc['before']}% → ${mc['after']}%'),
          actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Keep going'))],
        ),
      );

  Future<void> _replan() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Re-plan?'),
        content: const Text('Builds a fresh plan from your current profile and questionnaire answers. '
            'Skills you finished are skipped, and ticks on tasks that are still in the plan are kept.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Re-plan')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _replanning = true);
    try {
      final r = await api.post('/roadmap', {});
      _changed = true;
      setState(() => _plan = r);
      _snack('New plan ready');
    } catch (e) {
      _snack('$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _replanning = false);
    }
  }

  Future<void> _open(String url) async {
    if (!await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication)) _snack('Could not open link');
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width > 900;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            title: Text('Roadmap: ${_plan['role']}'),
            actions: [
              IconButton(
                tooltip: 'Re-plan',
                onPressed: _replanning ? null : _replan,
                icon: _replanning
                    ? const SizedBox(
                        width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : const Icon(Icons.autorenew),
              ),
            ],
            bottom: const TabBar(
              labelColor: Colors.white,
              unselectedLabelColor: Colors.white70,
              indicatorColor: Colors.white,
              tabs: [Tab(text: 'Weekly plan'), Tab(text: 'Skills')],
            ),
          ),
          body: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: wide ? 900 : double.infinity),
              child: TabBarView(children: [_weeksTab(), _skillsTab()]),
            ),
          ),
        ),
      ),
    );
  }

  // ----------------------------------------------------------- weekly plan --
  Widget _weeksTab() {
    final current = _progress['current_week'] as int?;
    return ListView(padding: const EdgeInsets.all(16), children: [
      _progressCard(),
      for (final w in _weeks) _weekCard(w, current),
      if (((_plan['later'] as List?) ?? []).isNotEmpty)
        SectionCard(
          title: 'After this plan',
          icon: Icons.more_time,
          child: Text((_plan['later'] as List).map((l) => (l as Map)['name']).join(', ')),
        ),
    ]);
  }

  Widget _progressCard() {
    final p = _progress;
    final color = switch (p['status']) {
      'behind' => AppColors.bad,
      'ahead' || 'done' => AppColors.good,
      _ => AppColors.brand,
    };
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(children: [
          ScoreGauge(score: p['percent'] as num, label: 'done', size: 96),
          const SizedBox(width: 16),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(p['status'] == 'behind' ? Icons.warning_amber : Icons.check_circle_outline, color: color),
                const SizedBox(width: 6),
                Expanded(child: Text(p['message'] as String, style: TextStyle(color: color, fontWeight: FontWeight.w600))),
              ]),
              const SizedBox(height: 8),
              Text('${p['hours_done']} of ${p['hours_total']} hours · '
                  '${p['tasks_done']}/${p['tasks_total']} tasks · '
                  '${p['skills_completed']} skill(s) learned'),
              const SizedBox(height: 4),
              Text((_plan['summary'] as Map)['message'] as String,
                  style: const TextStyle(fontSize: 12, color: Colors.grey)),
            ]),
          ),
        ]),
      ),
    );
  }

  Widget _weekCard(Map<String, dynamic> w, int? current) {
    final tasks = (w['tasks'] as List).cast<Map<String, dynamic>>();
    final done = tasks.where((t) => t['done'] == true).length;
    final isCurrent = w['week'] == current;
    final finished = done == tasks.length;
    return Card(
      shape: isCurrent
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16), side: const BorderSide(color: AppColors.brand, width: 2))
          : null,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: isCurrent,
          leading: CircleAvatar(
            backgroundColor: finished ? AppColors.good : AppColors.brand.withValues(alpha: isCurrent ? 1 : 0.15),
            foregroundColor: finished || isCurrent ? Colors.white : AppColors.brand,
            child: finished ? const Icon(Icons.check) : Text('${w['week']}'),
          ),
          title: Text('Week ${w['week']}${isCurrent ? '  ·  this week' : ''}'),
          subtitle: Text('$done/${tasks.length} tasks · ${w['hours']} h · '
              '${tasks.map((t) => t['skill']).toSet().join(', ')}'),
          children: [for (final t in tasks) _taskTile(t)],
        ),
      ),
    );
  }

  Widget _taskTile(Map<String, dynamic> t) {
    final saving = _saving.contains(t['id']);
    final icon = switch (t['step']) {
      'learn' => Icons.menu_book,
      'practise' => Icons.fitness_center,
      _ => Icons.construction,
    };
    return CheckboxListTile(
      value: t['done'] == true,
      onChanged: saving ? null : (v) => _toggle(t, v ?? false),
      secondary: Icon(icon, color: Colors.grey),
      title: Text(t['title'] as String,
          style: TextStyle(
              decoration: t['done'] == true ? TextDecoration.lineThrough : null,
              color: t['done'] == true ? Colors.grey : null)),
      subtitle: Text('${t['hours']} h · ${t['skill']}'),
      controlAffinity: ListTileControlAffinity.trailing,
    );
  }

  // ---------------------------------------------------------------- skills --
  Widget _skillsTab() {
    final completed = _completed;
    final done = ((_plan['completed_skills'] as List?) ?? []).cast<Map<String, dynamic>>();
    return ListView(padding: const EdgeInsets.all(16), children: [
      const Padding(
        padding: EdgeInsets.only(bottom: 8),
        child: Text('In learning order. Foundations come before the skills that need them.',
            style: TextStyle(color: Colors.grey)),
      ),
      for (final (i, s) in _skills.indexed) _skillCard(i + 1, s, completed.contains(s['name'])),
      if (done.any((c) => !_skills.any((s) => s['name'] == c['name'])))
        SectionCard(
          title: 'Learned in earlier plans',
          icon: Icons.emoji_events_outlined,
          child: Text(done.where((c) => !_skills.any((s) => s['name'] == c['name'])).map((c) => c['name']).join(', ')),
        ),
    ]);
  }

  Widget _skillCard(int n, Map<String, dynamic> s, bool learned) {
    final kind = s['kind'] as String;
    final pre = (s['prerequisites'] as List? ?? []).cast<String>();
    final share = s['share_of_postings'] as num?;
    return Card(
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          leading: CircleAvatar(
            backgroundColor: learned ? AppColors.good : Colors.grey.shade200,
            foregroundColor: learned ? Colors.white : Colors.black87,
            child: learned ? const Icon(Icons.check) : Text('$n'),
          ),
          title: Text(s['name'] as String),
          subtitle: Text([
            switch (kind) { 'foundation' => 'Foundation', 'improve' => 'Improve', _ => 'New skill' },
            if (s['level'] != null)
              switch (s['level'] as int) { 1 => 'Basic', 2 => 'Core', 3 => 'Advanced', _ => 'Whole field' },
            '${s['hours']} h',
            if (share != null) 'in ${(share * 100).round()}% of postings',
          ].join(' · ')),
          childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (pre.isNotEmpty) Text('Learn first: ${pre.join(', ')}', style: const TextStyle(color: Colors.grey)),
            const SizedBox(height: 6),
            Text('Project: ${s['project']}', style: const TextStyle(fontWeight: FontWeight.w600)),
            if (s['tip'] != null) ...[const SizedBox(height: 4), Text('Tip: ${s['tip']}')],
            const SizedBox(height: 8),
            // Real videos (from YouTube) as a list with channel names; other links as chips
            for (final v in (s['resources'] as List).cast<Map<String, dynamic>>().where((r) => r['channel'] != null))
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.play_circle_fill, color: Colors.red),
                title: Text(v['title'] as String, maxLines: 2, overflow: TextOverflow.ellipsis),
                subtitle: Text('YouTube · ${v['channel']}'),
                onTap: () => _open(v['url'] as String),
              ),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final r in (s['resources'] as List).cast<Map<String, dynamic>>().where((r) => r['channel'] == null))
                ActionChip(
                  avatar: Icon(
                      switch (r['type']) {
                        'video' => Icons.play_circle_outline,
                        'course' => Icons.school_outlined,
                        'projects' => Icons.lightbulb_outline,
                        _ => Icons.article_outlined,
                      },
                      size: 18),
                  label: Text(r['title'] as String, style: const TextStyle(fontSize: 12)),
                  onPressed: () => _open(r['url'] as String),
                ),
            ]),
          ],
        ),
      ),
    );
  }
}
