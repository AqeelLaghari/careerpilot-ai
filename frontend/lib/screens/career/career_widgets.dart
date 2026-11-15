import 'dart:async';

import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../resume/resume_widgets.dart';

/// Small labelled percentage bar.
class MiniBar extends StatelessWidget {
  const MiniBar({super.key, required this.label, required this.value});
  final String label;
  final num value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 4),
    child: Row(
      children: [
        SizedBox(
          width: 72,
          child: Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        ),
        Expanded(
          child: LinearProgressIndicator(
            value: value / 100,
            minHeight: 5,
            borderRadius: BorderRadius.circular(3),
            color: AppColors.forScore(value),
            backgroundColor: Colors.grey.shade200,
          ),
        ),
        SizedBox(
          width: 40,
          child: Text('${value.round()}%', textAlign: TextAlign.right, style: const TextStyle(fontSize: 12)),
        ),
      ],
    ),
  );
}

Widget skillChips(List<String> skills, {IconData? icon}) => Wrap(
  spacing: 6,
  runSpacing: 6,
  children: [
    for (final s in skills)
      Chip(
        label: Text(s, style: const TextStyle(fontSize: 12)),
        avatar: icon == null ? null : Icon(icon, size: 16),
        visualDensity: VisualDensity.compact,
      ),
  ],
);

/// "Answer N quick questions" call-to-action.
class QuestionnaireBanner extends StatelessWidget {
  const QuestionnaireBanner({super.key, required this.remaining, required this.answered, required this.onStart});
  final int remaining;
  final int answered;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) => Card(
    color: AppColors.brand.withValues(alpha: 0.06),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Icon(Icons.quiz_outlined, color: AppColors.brand, size: 36),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  answered == 0 ? 'Personalise your plan' : 'Finish your questions',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                Text(
                  '$remaining quick question${remaining == 1 ? '' : 's'}, only about what your CV '
                  'doesn\'t already tell us.',
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(onPressed: onStart, child: Text(answered == 0 ? 'Start' : 'Continue')),
        ],
      ),
    ),
  );
}

/// The chosen target role: score + bars + skills to add.
class TargetSummary extends StatelessWidget {
  const TargetSummary({super.key, required this.match});
  final Map<String, dynamic>? match;

  @override
  Widget build(BuildContext context) {
    final m = match;
    if (m == null) return const SizedBox.shrink();
    final score = m['score'] as num;
    final missing = (m['missing_skills'] as List).cast<String>();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(m['role'] as String, style: Theme.of(context).textTheme.titleLarge)),
            Text(
              '${score.round()}%',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.forScore(score)),
            ),
          ],
        ),
        Text('Learned from ${m['postings_analysed']} job postings', style: const TextStyle(color: Colors.grey)),
        const SizedBox(height: 10),
        MiniBar(label: 'Keywords', value: m['keyword'] as num),
        MiniBar(label: 'Meaning', value: m['semantic'] as num),
        if (missing.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text(
            'Skills employers want that your profile doesn\'t show yet:',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          skillChips(missing, icon: Icons.add),
        ],
      ],
    );
  }
}

/// One best-fit career, expandable to show matched / missing skills.
class CareerMatchTile extends StatelessWidget {
  const CareerMatchTile({
    super.key,
    required this.rank,
    required this.match,
    required this.isTarget,
    required this.busy,
    required this.onSetTarget,
  });
  final int rank;
  final Map<String, dynamic> match;
  final bool isTarget;
  final bool busy;
  final VoidCallback onSetTarget;

  @override
  Widget build(BuildContext context) {
    final score = match['score'] as num;
    final matched = (match['matched_skills'] as List).cast<String>();
    final missing = (match['missing_skills'] as List).cast<String>();
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        leading: CircleAvatar(
          backgroundColor: AppColors.forScore(score).withValues(alpha: 0.15),
          child: Text(
            '${score.round()}',
            style: TextStyle(color: AppColors.forScore(score), fontWeight: FontWeight.bold),
          ),
        ),
        title: Text('$rank. ${match['role']}'),
        subtitle: Wrap(
          spacing: 6,
          children: [
            Text('${match['postings_analysed']} postings', style: const TextStyle(fontSize: 12)),
            if (isTarget) Text('· your target', style: TextStyle(fontSize: 12, color: AppColors.good)),
            if (match['interest_match'] == true)
              Text('· matches your interests', style: TextStyle(fontSize: 12, color: AppColors.brand)),
          ],
        ),
        childrenPadding: const EdgeInsets.only(left: 8, bottom: 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          MiniBar(label: 'Keywords', value: match['keyword'] as num),
          MiniBar(label: 'Meaning', value: match['semantic'] as num),
          if (matched.isNotEmpty) ...[
            const SizedBox(height: 6),
            const Text('You have', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            skillChips(matched, icon: Icons.check),
          ],
          if (missing.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('To learn', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            skillChips(missing, icon: Icons.add),
          ],
          const SizedBox(height: 8),
          if (!isTarget)
            OutlinedButton.icon(
              onPressed: busy ? null : onSetTarget,
              icon: busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.flag_outlined),
              label: const Text('Set as my target'),
            ),
        ],
      ),
    );
  }
}

/// Search all learned roles (e.g. "nurse", "accountant") and pick one.
class RoleSearchDialog extends StatefulWidget {
  const RoleSearchDialog({super.key});

  @override
  State<RoleSearchDialog> createState() => _RoleSearchDialogState();
}

class _RoleSearchDialogState extends State<RoleSearchDialog> {
  List<Map<String, dynamic>> _roles = [];
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _search('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _search(String q) async {
    try {
      final r = await api.getList('/market/roles?limit=30&q=${Uri.encodeQueryComponent(q)}');
      if (mounted) setState(() => _roles = r.cast<Map<String, dynamic>>());
    } catch (_) {
      /* keep old list */
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Choose a target role'),
    content: SizedBox(
      width: 420,
      height: 420,
      child: Column(
        children: [
          TextField(
            autofocus: true,
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'e.g. data analyst, nurse'),
            onChanged: (q) {
              _debounce?.cancel();
              _debounce = Timer(const Duration(milliseconds: 250), () => _search(q));
            },
          ),
          const SizedBox(height: 8),
          Expanded(
            child: _roles.isEmpty
                ? const Center(child: Text('No roles found'))
                : ListView(
                    children: [
                      for (final r in _roles)
                        ListTile(
                          title: Text(r['role'] as String),
                          subtitle: Text('${r['postings']} job postings'),
                          onTap: () => Navigator.pop(context, r['role'] as String),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    ),
    actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel'))],
  );
}

/// Roadmap summary + progress; "Open roadmap" goes to the interactive week-by-week screen.
class RoadmapSummaryCard extends StatelessWidget {
  const RoadmapSummaryCard({
    super.key,
    required this.roadmap,
    required this.building,
    required this.onBuild,
    required this.onOpen,
  });
  final Map<String, dynamic>? roadmap;
  final bool building;
  final VoidCallback onBuild;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final r = roadmap;
    final button = FilledButton.icon(
      onPressed: building ? null : onBuild,
      icon: building
          ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
          : Icon(r == null ? Icons.route : Icons.refresh),
      label: Text(r == null ? 'Build my roadmap' : 'Rebuild'),
    );
    if (r == null) {
      return SectionCard(
        title: 'Learning roadmap',
        icon: Icons.route_outlined,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'A week-by-week plan to learn the skills your target role needs, '
              'in the right order, fitted to your weekly hours.',
            ),
            const SizedBox(height: 12),
            button,
          ],
        ),
      );
    }
    final s = r['summary'] as Map<String, dynamic>;
    final p = r['progress'] as Map<String, dynamic>?;
    final skills = (r['skills'] as List).cast<Map<String, dynamic>>();
    final later = (r['later'] as List? ?? []).cast<Map<String, dynamic>>();
    return SectionCard(
      title: 'Roadmap: ${r['role']}',
      icon: Icons.route_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 16,
            runSpacing: 8,
            children: [
              _stat('${s['weeks_needed']}', 'weeks'),
              _stat('${s['hours_per_week']} h', 'per week'),
              _stat('${skills.length}', 'skills'),
            ],
          ),
          const SizedBox(height: 10),
          if (p != null) ...[
            LinearProgressIndicator(
              value: (p['percent'] as num) / 100,
              minHeight: 8,
              borderRadius: BorderRadius.circular(4),
              color: p['status'] == 'behind' ? AppColors.bad : AppColors.good,
              backgroundColor: Colors.grey.shade200,
            ),
            const SizedBox(height: 4),
            Text('${p['percent']}% done · ${p['message']}', style: const TextStyle(fontSize: 12)),
            const SizedBox(height: 8),
          ],
          Text(s['message'] as String),
          const SizedBox(height: 12),
          const Text('Learning order', style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          for (final (i, sk) in skills.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                children: [
                  SizedBox(
                    width: 24,
                    child: Text('${i + 1}.', style: const TextStyle(color: Colors.grey)),
                  ),
                  Expanded(child: Text(sk['name'] as String)),
                  if (sk['kind'] == 'foundation')
                    Text('foundation ', style: TextStyle(fontSize: 11, color: AppColors.brand)),
                  if (sk['kind'] == 'improve') Text('improve ', style: TextStyle(fontSize: 11, color: AppColors.warn)),
                  Text('${sk['hours']} h', style: const TextStyle(fontSize: 12, color: Colors.grey)),
                ],
              ),
            ),
          if (later.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'After this plan: ${later.map((l) => l['name']).join(', ')}',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed: onOpen,
                icon: const Icon(Icons.checklist),
                label: const Text('Open roadmap'),
              ),
              OutlinedButton.icon(
                onPressed: building ? null : onBuild,
                icon: building
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.autorenew),
                label: const Text('Re-plan'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _stat(String value, String label) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        value,
        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.brand),
      ),
      Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
    ],
  );
}

/// Paste any job description → match % + skills you have / are missing.
class JobDescriptionCard extends StatefulWidget {
  const JobDescriptionCard({super.key});

  @override
  State<JobDescriptionCard> createState() => _JobDescriptionCardState();
}

class _JobDescriptionCardState extends State<JobDescriptionCard> {
  final _ctrl = TextEditingController();
  Map<String, dynamic>? _result;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _match() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final r = await api.post('/career/jd-match', {'job_description': _ctrl.text.trim()});
      setState(() => _result = r);
    } catch (e) {
      setState(() => _error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _result;
    return SectionCard(
      title: 'Match a job ad',
      icon: Icons.content_paste_search,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Found a job you like? Paste its description to see how well you match.'),
          const SizedBox(height: 10),
          TextField(
            controller: _ctrl,
            minLines: 4,
            maxLines: 10,
            decoration: const InputDecoration(border: OutlineInputBorder(), hintText: 'Paste the job description here'),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Text(
                _ctrl.text.trim().length < 50 ? 'At least 50 characters' : '',
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const Spacer(),
              FilledButton(
                onPressed: _busy || _ctrl.text.trim().length < 50 ? null : _match,
                child: _busy
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Check match'),
              ),
            ],
          ),
          if (_error != null) Text(_error!, style: TextStyle(color: AppColors.bad)),
          if (r != null) ...[
            const Divider(height: 24),
            Row(
              children: [
                const Expanded(
                  child: Text('Your match', style: TextStyle(fontWeight: FontWeight.w600)),
                ),
                Text(
                  '${(r['score'] as num).round()}%',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: AppColors.forScore(r['score'] as num),
                  ),
                ),
              ],
            ),
            MiniBar(label: 'Keywords', value: r['keyword'] as num),
            MiniBar(label: 'Meaning', value: r['semantic'] as num),
            const SizedBox(height: 6),
            Text(
              '${r['skills_in_job']} skills found in the job ad',
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            if ((r['matched_skills'] as List).isNotEmpty) ...[
              const SizedBox(height: 8),
              const Text('You have', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              skillChips((r['matched_skills'] as List).cast<String>(), icon: Icons.check),
            ],
            if ((r['missing_skills'] as List).isNotEmpty) ...[
              const SizedBox(height: 8),
              const Text('Missing', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              skillChips((r['missing_skills'] as List).cast<String>(), icon: Icons.add),
            ],
          ],
        ],
      ),
    );
  }
}
