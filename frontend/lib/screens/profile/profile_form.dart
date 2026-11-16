import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../data/universities.dart';
import '../../services/api_client.dart';
import '../../services/profile_store.dart';
import '../../theme.dart';
import '../../widgets/user_avatar.dart';

/// The values of the profile form, shared by the sign-up steps and "My profile".
class ProfileFormData extends ChangeNotifier {
  ProfileFormData(Map<String, dynamic> start) {
    String s(String k) => '${start[k] ?? ''}';
    name.text = s('full_name');
    university.text = s('university');
    degree.text = s('degree');
    city.text = s('city');
    targetRole.text = s('target_role');
    linkedin.text = s('linkedin');
    github.text = s('github');
    phone.text = s('phone');
    status = start['status'] as String?;
    semester = start['semester'] as int?;
    graduationYear = start['graduation_year'] as int?;
  }

  final name = TextEditingController();
  final university = TextEditingController();
  final degree = TextEditingController();
  final city = TextEditingController();
  final targetRole = TextEditingController();
  final linkedin = TextEditingController();
  final github = TextEditingController();
  final phone = TextEditingController();
  String? status;
  int? semester;
  int? graduationYear;
  Map<String, String> errors = {};

  static const aboutFields = {'full_name', 'status', 'university', 'degree', 'semester', 'graduation_year', 'city'};

  void set(void Function() change) {
    change();
    notifyListeners();
  }

  void showErrors(Map<String, String> e) => set(() => errors = e);

  Map<String, dynamic> about() => {
    'full_name': name.text.trim(),
    'status': status,
    'university': university.text.trim(),
    'degree': degree.text.trim(),
    'semester': status == 'student' ? semester : null,
    'graduation_year': graduationYear,
    'city': city.text.trim(),
  };

  Map<String, dynamic> career() => {
    'target_role': targetRole.text.trim(),
    'linkedin': linkedin.text.trim(),
    'github': github.text.trim(),
    'phone': phone.text.trim(),
  };

  /// Simple checks before sending (the server checks everything again).
  Map<String, String> checkAbout() => {
    if (name.text.trim().length < 2) 'full_name': 'Enter your name',
    if (status == null) 'status': 'Choose one',
    if (university.text.trim().isEmpty) 'university': 'Enter your university or college',
  };

  @override
  void dispose() {
    for (final c in [name, university, degree, city, targetRole, linkedin, github, phone]) {
      c.dispose();
    }
    super.dispose();
  }
}

InputDecoration _deco(String label, IconData icon, String? error, {String? hint}) => InputDecoration(
  labelText: label,
  hintText: hint,
  prefixIcon: Icon(icon),
  errorText: error,
  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
);

/// Photo, name, student/graduate/professional, university, degree, semester / year, city.
class AboutYouSection extends StatelessWidget {
  const AboutYouSection({super.key, required this.data});
  final ProfileFormData data;

  @override
  Widget build(BuildContext context) {
    final year = DateTime.now().year;
    return ListenableBuilder(
      listenable: data,
      builder: (context, _) {
        final e = data.errors;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Center(child: PhotoPicker()),
            const SizedBox(height: 24),
            TextField(
              controller: data.name,
              autofillHints: const [AutofillHints.name],
              decoration: _deco('Full name', Icons.person_outline, e['full_name']),
            ),
            const SizedBox(height: 18),
            Text('I am a', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in profileStore.statuses.entries)
                  ChoiceChip(
                    label: Text(entry.value),
                    avatar: Icon(switch (entry.key) {
                      'student' => Icons.school_outlined,
                      'graduate' => Icons.workspace_premium_outlined,
                      _ => Icons.work_outline,
                    }, size: 18),
                    selected: data.status == entry.key,
                    onSelected: (_) => data.set(() => data.status = entry.key),
                  ),
              ],
            ),
            if (e['status'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(e['status']!, style: TextStyle(color: AppColors.bad, fontSize: 12)),
              ),
            const SizedBox(height: 18),
            Autocomplete<String>(
              initialValue: TextEditingValue(text: data.university.text),
              optionsBuilder: (v) {
                final q = v.text.toLowerCase().trim();
                if (q.length < 2) return const Iterable<String>.empty();
                return pakistaniUniversities.where((u) => u.toLowerCase().contains(q)).take(8);
              },
              onSelected: (u) => data.university.text = u,
              fieldViewBuilder: (context, controller, focus, onSubmit) {
                return TextField(
                  controller: controller,
                  focusNode: focus,
                  onChanged: (t) => data.university.text = t,
                  decoration: _deco(
                    data.status == 'professional' ? 'University / college (last studied)' : 'University / college',
                    Icons.account_balance_outlined,
                    e['university'],
                    hint: 'Start typing to search',
                  ),
                );
              },
            ),
            const SizedBox(height: 14),
            TextField(
              controller: data.degree,
              decoration: _deco(
                'Degree / programme',
                Icons.menu_book_outlined,
                e['degree'],
                hint: 'e.g. BS Software Engineering',
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                if (data.status == 'student') ...[
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      initialValue: data.semester,
                      decoration: _deco('Semester', Icons.timeline, e['semester']),
                      items: [for (var s = 1; s <= 12; s++) DropdownMenuItem(value: s, child: Text('Semester $s'))],
                      onChanged: (v) => data.set(() => data.semester = v),
                    ),
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  child: DropdownButtonFormField<int>(
                    initialValue: data.graduationYear,
                    decoration: _deco(
                      data.status == 'student' ? 'Expected graduation' : 'Graduation year',
                      Icons.event_outlined,
                      e['graduation_year'],
                    ),
                    items: [for (var y = year + 6; y >= year - 40; y--) DropdownMenuItem(value: y, child: Text('$y'))],
                    onChanged: (v) => data.set(() => data.graduationYear = v),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            TextField(
              controller: data.city,
              autofillHints: const [AutofillHints.addressCity],
              decoration: _deco('City', Icons.location_on_outlined, e['city'], hint: 'e.g. Karachi'),
            ),
          ],
        );
      },
    );
  }
}

/// Target role, LinkedIn, GitHub, phone (all optional).
class CareerSection extends StatefulWidget {
  const CareerSection({super.key, required this.data});
  final ProfileFormData data;

  @override
  State<CareerSection> createState() => _CareerSectionState();
}

class _CareerSectionState extends State<CareerSection> {
  List<String> _roles = [];

  @override
  void initState() {
    super.initState();
    api
        .getList('/market/roles?limit=200')
        .then((r) {
          if (mounted) setState(() => _roles = r.map((x) => x is Map ? '${x['role'] ?? x['name']}' : '$x').toList());
        })
        .catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.data;
    return ListenableBuilder(
      listenable: data,
      builder: (context, _) {
        final e = data.errors;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Autocomplete<String>(
              initialValue: TextEditingValue(text: data.targetRole.text),
              optionsBuilder: (v) {
                final q = v.text.toLowerCase().trim();
                if (q.isEmpty) return const Iterable<String>.empty();
                return _roles.where((r) => r.toLowerCase().contains(q)).take(8);
              },
              onSelected: (r) => data.targetRole.text = r,
              fieldViewBuilder: (context, controller, focus, _) {
                return TextField(
                  controller: controller,
                  focusNode: focus,
                  onChanged: (t) => data.targetRole.text = t,
                  decoration: _deco('Target role', Icons.flag_outlined, e['target_role'], hint: 'e.g. Data Scientist'),
                );
              },
            ),
            const SizedBox(height: 14),
            TextField(
              controller: data.linkedin,
              keyboardType: TextInputType.url,
              decoration: _deco('LinkedIn profile', Icons.link, e['linkedin'], hint: 'linkedin.com/in/your-name'),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: data.github,
              keyboardType: TextInputType.url,
              decoration: _deco('GitHub profile', Icons.code, e['github'], hint: 'github.com/your-name'),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: data.phone,
              keyboardType: TextInputType.phone,
              autofillHints: const [AutofillHints.telephoneNumber],
              decoration: _deco('Phone (optional)', Icons.phone_outlined, e['phone'], hint: '+92 3xx xxxxxxx'),
            ),
            const SizedBox(height: 8),
            Text(
              'Only you can see these. They are never sent to the AI.',
              style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            ),
          ],
        );
      },
    );
  }
}

/// The round photo with "Upload photo" / "Remove". The image is shrunk on the device first.
class PhotoPicker extends StatefulWidget {
  const PhotoPicker({super.key});

  @override
  State<PhotoPicker> createState() => _PhotoPickerState();
}

class _PhotoPickerState extends State<PhotoPicker> {
  bool _busy = false;

  Future<void> _pick() async {
    final file = await FilePicker.pickFile(type: FileType.image);
    if (file == null) return;
    setState(() => _busy = true);
    try {
      final bytes = await file.readAsBytes();
      if (bytes.length > 15 * 1024 * 1024) throw const FormatException('Please choose a photo under 15 MB.');
      await profileStore.uploadPhoto(bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('$e'.replaceFirst('FormatException: ', '').replaceFirst(RegExp(r'API error \d+: '), '')),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: profileStore,
      builder: (context, _) => Column(
        children: [
          Stack(
            children: [
              const UserAvatar(radius: 48),
              Positioned(
                right: 0,
                bottom: 0,
                child: Material(
                  color: AppColors.brand,
                  shape: const CircleBorder(),
                  child: IconButton(
                    tooltip: 'Upload photo',
                    icon: _busy
                        ? SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.onBrand),
                          )
                        : Icon(Icons.photo_camera, color: AppColors.onBrand, size: 18),
                    onPressed: _busy ? null : _pick,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextButton(
                onPressed: _busy ? null : _pick,
                child: Text(profileStore.photo == null ? 'Upload photo' : 'Change photo'),
              ),
              if (profileStore.photo != null)
                TextButton(
                  onPressed: _busy ? null : profileStore.removePhoto,
                  child: Text('Remove', style: TextStyle(color: AppColors.bad)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
