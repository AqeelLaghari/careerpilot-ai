import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import '../career/career_screen.dart' show EmptyHint;

/// Live remote jobs a Pakistani can apply to, best match with the user's CV first.
/// Every job shows its source (link back) and Apply opens the original posting.
class JobsScreen extends StatefulWidget {
  const JobsScreen({super.key});

  @override
  State<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends State<JobsScreen> {
  bool _loading = true;
  bool _noResume = false;
  String? _error;
  Map<String, dynamic>? _data;
  String _query = '';
  bool _strongOnly = false;
  Timer? _retry;
  int _retries = 0;
  final _search = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _retry?.cancel();
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool quiet = false}) async {
    if (!quiet) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final q = _query.isEmpty ? '' : '?q=${Uri.encodeQueryComponent(_query)}';
      final d = await api.get('/jobs$q');
      if (!mounted) return;
      setState(() {
        _data = d;
        _noResume = false;
      });
      // The first fetch of the day runs in the background on the server: check back soon.
      _retry?.cancel();
      final empty = (d['jobs'] as List).isEmpty;
      if ((d['refreshing'] == true || empty) && _retries < 8 && _query.isEmpty) {
        _retries++;
        _retry = Timer(const Duration(seconds: 15), () => _load(quiet: true));
      }
    } catch (e) {
      if (!mounted) return;
      final msg = '$e'.replaceFirst('Exception: ', '').replaceFirst(RegExp(r'API error \d+: '), '');
      setState(() => msg.toLowerCase().contains('upload a resume') ? _noResume = true : _error = msg);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(String? url) async {
    if (url == null) return;
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the link')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _data == null) return const Center(child: CircularProgressIndicator());
    if (_noResume) {
      return const EmptyHint(
        icon: Icons.upload_file,
        title: 'Upload your resume first',
        text: 'Jobs are ranked by how well they match your CV.',
      );
    }
    if (_error != null && _data == null) {
      return EmptyHint(
        icon: Icons.cloud_off,
        title: 'Could not load jobs',
        text: _error!,
        action: FilledButton(onPressed: _load, child: const Text('Try again')),
      );
    }
    final d = _data!;
    var jobs = (d['jobs'] as List).cast<Map<String, dynamic>>();
    if (_strongOnly) jobs = jobs.where((j) => (j['match'] as num) >= 50).toList();
    final sources = (d['sources'] as List).cast<Map<String, dynamic>>();

    return RefreshIndicator(
      onRefresh: () => _load(quiet: true),
      child: ListView(padding: const EdgeInsets.all(16), children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Remote jobs open to Pakistan', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 4),
              Text(
                [
                  if (d['role'] != null) 'Best match for you first (${d['role']})',
                  '${d['jobs_available']} jobs',
                  if (d['updated_at'] != null) 'updated ${_ago(d['updated_at'] as num)}',
                ].join(' · '),
                style: const TextStyle(color: Colors.grey),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _search,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  hintText: 'Search a job title, company or skill',
                  prefixIcon: const Icon(Icons.search),
                  border: const OutlineInputBorder(),
                  isDense: true,
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.clear),
                          onPressed: () {
                            _search.clear();
                            _query = '';
                            _load();
                          }),
                ),
                onSubmitted: (v) {
                  _query = v.trim();
                  _load();
                },
              ),
              const SizedBox(height: 8),
              FilterChip(
                label: const Text('Strong matches only (50%+)'),
                selected: _strongOnly,
                onSelected: (v) => setState(() => _strongOnly = v),
              ),
              const SizedBox(height: 8),
              if (jobs.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 32),
                  child: Center(
                    child: Column(children: [
                      if (d['refreshing'] == true) ...[
                        const CircularProgressIndicator(),
                        const SizedBox(height: 12),
                        const Text('Fetching fresh remote jobs… this takes about a minute the first time.'),
                      ] else
                        Text(_query.isEmpty
                            ? 'No jobs yet. Pull down to refresh.'
                            : 'No jobs match "$_query". Try another word.'),
                    ]),
                  ),
                )
              else
                for (final j in jobs) _JobCard(job: j, onOpen: _open),
              const SizedBox(height: 16),
              // Attribution: every source is named and linked, as their API terms ask.
              Wrap(crossAxisAlignment: WrapCrossAlignment.center, spacing: 4, children: [
                const Text('Jobs from', style: TextStyle(color: Colors.grey, fontSize: 12)),
                for (final s in sources)
                  TextButton(
                    style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                    onPressed: () => _open(s['url'] as String),
                    child: Text(s['name'] as String, style: const TextStyle(fontSize: 12)),
                  ),
              ]),
              const Text(
                'Always check the location rules on the original posting before applying.',
                style: TextStyle(color: Colors.grey, fontSize: 12),
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}

String _ago(num epochSeconds) {
  final d = DateTime.now().difference(DateTime.fromMillisecondsSinceEpoch((epochSeconds * 1000).round()));
  if (d.inMinutes < 1) return 'just now';
  if (d.inHours < 1) return '${d.inMinutes} min ago';
  if (d.inDays < 1) return '${d.inHours} h ago';
  return '${d.inDays} d ago';
}

class _JobCard extends StatelessWidget {
  const _JobCard({required this.job, required this.onOpen});
  final Map<String, dynamic> job;
  final void Function(String?) onOpen;

  static (String, IconData, Color) _badge(String? scope) => switch (scope) {
        'Pakistan' => ('Open to Pakistan', Icons.check_circle, AppColors.good),
        'Worldwide' => ('Open worldwide', Icons.public, AppColors.good),
        'Asia' => ('Open to Asia', Icons.public, AppColors.good),
        'Time zone fits Pakistan' => ('Time zone fits Pakistan', Icons.schedule, AppColors.good),
        _ => ('Location not stated: check posting', Icons.help_outline, AppColors.warn),
      };

  @override
  Widget build(BuildContext context) {
    final match = job['match'] as num;
    final matched = (job['matched_skills'] as List).cast<String>();
    final missing = (job['missing_skills'] as List).cast<String>();
    final (label, icon, color) = _badge(job['scope'] as String?);
    final meta = [
      job['company'],
      if (job['job_type'] != null) job['job_type'],
      if (job['salary'] != null) job['salary'],
      if (job['published_at'] != null) 'posted ${_ago(job['published_at'] as num)}',
    ].join(' · ');
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(job['title'] as String, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(meta, style: const TextStyle(color: Colors.grey)),
              ]),
            ),
            const SizedBox(width: 8),
            Column(children: [
              Text('${match.round()}%',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppColors.forScore(match))),
              const Text('match', style: TextStyle(fontSize: 11, color: Colors.grey)),
            ]),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 4),
            Flexible(child: Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 13))),
          ]),
          if (matched.isNotEmpty || missing.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final s in matched)
                Chip(
                  label: Text(s, style: const TextStyle(fontSize: 12)),
                  avatar: const Icon(Icons.check, size: 14, color: AppColors.good),
                  visualDensity: VisualDensity.compact,
                ),
              for (final s in missing)
                Chip(
                  label: Text(s, style: const TextStyle(fontSize: 12, color: Colors.black54)),
                  avatar: const Icon(Icons.add, size: 14),
                  visualDensity: VisualDensity.compact,
                  backgroundColor: Colors.grey.shade100,
                ),
            ]),
          ],
          if ((job['excerpt'] as String).isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(job['excerpt'] as String, maxLines: 3, overflow: TextOverflow.ellipsis),
          ],
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
            FilledButton.icon(
              onPressed: () => onOpen(job['apply_url'] as String?),
              icon: const Icon(Icons.open_in_new, size: 18),
              label: const Text('Apply'),
            ),
            TextButton(
              onPressed: () => onOpen(job['url'] as String?),
              child: Text('View on ${job['source_name']}'),
            ),
          ]),
        ]),
      ),
    );
  }
}
