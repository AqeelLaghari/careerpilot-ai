import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import '../../theme.dart';
import 'resume_widgets.dart';

/// Resume Intelligence screen: upload a PDF → ATS score, fixes, extracted profile.
class ResumeScreen extends StatefulWidget {
  const ResumeScreen({super.key});

  @override
  State<ResumeScreen> createState() => _ResumeScreenState();
}

class _ResumeScreenState extends State<ResumeScreen> {
  Map<String, dynamic>? _resume;
  bool _loading = true;
  bool _uploading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await api.getOrNull('/resume');
      if (mounted) setState(() => _resume = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickAndUpload() async {
    final file = await FilePicker.pickFile(type: FileType.custom, allowedExtensions: ['pdf']);
    if (file == null) return; // user cancelled
    setState(() {
      _uploading = true;
      _error = null;
    });
    try {
      final bytes = await file.readAsBytes();
      if (bytes.length > 5 * 1024 * 1024) throw Exception('File is larger than 5 MB.');
      final r = await api.uploadFile('/resume/upload', bytes, file.name);
      if (mounted) setState(() => _resume = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_uploading) {
      return const Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Analysing your resume…'),
          Text('Reading the PDF, extracting skills, scoring for ATS', style: TextStyle(color: Colors.grey)),
        ]),
      );
    }
    return _resume == null ? _emptyState() : _results(_resume!);
  }

  // ------------------------------------------------------------ empty state --
  Widget _emptyState() => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(children: [
              Icon(Icons.upload_file, size: 72, color: AppColors.brand.withValues(alpha: 0.7)),
              const SizedBox(height: 16),
              Text('Upload your resume', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text(
                'Get an ATS readability score, a list of fixes, and your skills extracted automatically. '
                'PDF only, up to 5 MB.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _pickAndUpload,
                icon: const Icon(Icons.picture_as_pdf),
                label: const Padding(padding: EdgeInsets.all(12), child: Text('Choose PDF')),
              ),
              if (_error != null) ...[const SizedBox(height: 16), _errorBox()],
            ]),
          ),
        ),
      );

  Widget _errorBox() => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
            color: AppColors.bad.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(12)),
        child: Row(children: [
          const Icon(Icons.error_outline, color: AppColors.bad),
          const SizedBox(width: 8),
          Expanded(child: Text(_error!)),
        ]),
      );

  // ----------------------------------------------------------------- results --
  Widget _results(Map<String, dynamic> r) {
    final ats = r['ats'] as Map<String, dynamic>;
    final e = r['entities'] as Map<String, dynamic>;
    final wide = MediaQuery.sizeOf(context).width > 900;

    final left = [
      _scoreCard(ats, r['filename'] as String? ?? ''),
      SectionCard(
        title: 'Top fixes',
        icon: Icons.build_circle_outlined,
        child: (ats['top_fixes'] as List).isEmpty
            ? const Text('Nothing to fix. Great job!')
            : Column(children: [
                for (final f in (ats['top_fixes'] as List).cast<Map<String, dynamic>>()) FixTile(fix: f),
              ]),
      ),
      SectionCard(
        title: 'Score breakdown',
        icon: Icons.analytics_outlined,
        child: Column(children: [
          for (final c in (ats['categories'] as List).cast<Map<String, dynamic>>()) CategoryTile(category: c),
        ]),
      ),
    ];
    final right = [
      _profileCard(e, r['contact'] as Map<String, dynamic>),
      SectionCard(
        title: 'Skills found (${(e['skills'] as List).length})',
        icon: Icons.psychology_outlined,
        child: SkillGroups(skills: (e['skills'] as List).cast<Map<String, dynamic>>()),
      ),
      _experienceCard(e),
      _educationCard(e),
      if ((e['projects'] as List).isNotEmpty) _projectsCard(e),
    ];

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null) _errorBox(),
          if (wide)
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: Column(children: left)),
              const SizedBox(width: 16),
              Expanded(child: Column(children: right)),
            ])
          else ...[...left, ...right],
        ],
      ),
    );
  }

  Widget _scoreCard(Map<String, dynamic> ats, String filename) => Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Wrap(
            spacing: 24,
            runSpacing: 16,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              ScoreGauge(score: ats['readability_score'] as num, label: ats['grade'] as String),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 320),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('ATS Readability', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(filename, style: const TextStyle(color: Colors.grey)),
                  const SizedBox(height: 8),
                  const Text('How easily applicant tracking systems can read your resume. '
                      'The role match score appears once you choose a target career.'),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: _pickAndUpload,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Upload new version'),
                  ),
                ]),
              ),
            ],
          ),
        ),
      );

  Widget _profileCard(Map<String, dynamic> e, Map<String, dynamic> contact) {
    final months = e['total_experience_months'] as int? ?? 0;
    String exp() => months == 0
        ? 'No work experience listed'
        : months < 12
            ? '$months months experience'
            : '${(months / 12).toStringAsFixed(1)} years experience';
    Widget row(IconData i, String? text) => text == null || text.isEmpty
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(children: [
              Icon(i, size: 18, color: Colors.grey),
              const SizedBox(width: 8),
              Expanded(child: Text(text)),
            ]),
          );
    return SectionCard(
      title: e['name'] as String? ?? 'Profile',
      icon: Icons.person_outline,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (e['headline'] != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(e['headline'] as String, style: Theme.of(context).textTheme.titleSmall),
          ),
        row(Icons.location_on_outlined, e['location'] as String?),
        row(Icons.email_outlined, contact['email'] as String?),
        row(Icons.phone_outlined, contact['phone'] as String?),
        row(Icons.link, contact['linkedin'] as String?),
        row(Icons.work_history_outlined, exp()),
        if ((e['languages'] as List).isNotEmpty) row(Icons.translate, (e['languages'] as List).join(', ')),
      ]),
    );
  }

  Widget _experienceCard(Map<String, dynamic> e) {
    final jobs = (e['experience'] as List).cast<Map<String, dynamic>>();
    return SectionCard(
      title: 'Experience',
      icon: Icons.work_outline,
      child: jobs.isEmpty
          ? const Text('No experience entries found.')
          : Column(children: [
              for (final j in jobs)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(j['title'] as String? ?? 'Role'),
                  subtitle: Text([
                    if (j['company'] != null) j['company'],
                    '${j['start']} – ${j['end']}',
                    if (j['months'] != null) '${j['months']} mo',
                  ].join(' · ')),
                  trailing: j['current'] == true
                      ? const Chip(label: Text('Current'), visualDensity: VisualDensity.compact)
                      : null,
                ),
            ]),
    );
  }

  Widget _educationCard(Map<String, dynamic> e) {
    final edu = (e['education'] as List).cast<Map<String, dynamic>>();
    return SectionCard(
      title: 'Education',
      icon: Icons.school_outlined,
      child: edu.isEmpty
          ? const Text('No education entries found.')
          : Column(children: [
              for (final d in edu)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(d['degree'] as String? ?? d['degree_level'] as String? ?? 'Degree'),
                  subtitle: Text([
                    if (d['institution'] != null) d['institution'],
                    if (d['end_year'] != null) '${d['expected'] == true ? 'Expected ' : ''}${d['end_year']}',
                    if (d['cgpa'] != null) 'CGPA ${d['cgpa']}',
                  ].join(' · ')),
                ),
            ]),
    );
  }

  Widget _projectsCard(Map<String, dynamic> e) {
    final projects = (e['projects'] as List).cast<Map<String, dynamic>>();
    return SectionCard(
      title: 'Projects',
      icon: Icons.rocket_launch_outlined,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final p in projects)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(p['title'] as String, style: const TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              Wrap(spacing: 4, runSpacing: 4, children: [
                for (final s in (p['skills'] as List))
                  Chip(
                    label: Text('$s', style: const TextStyle(fontSize: 11)),
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                  ),
              ]),
            ]),
          ),
      ]),
    );
  }
}
