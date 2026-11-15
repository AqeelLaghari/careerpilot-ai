import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show ThemeMode;
import 'package:image/image.dart' as img;

import 'api_client.dart';

/// The logged-in user's account profile and photo (Day 23), shared by every screen
/// (the top-bar menu, the dashboard, the profile page). Screens listen to it, so a new
/// photo or name shows up everywhere at once.
class ProfileStore extends ChangeNotifier {
  Map<String, dynamic> profile = {};
  Map<String, dynamic> suggested = {}; // pre-fill from the CV
  Map<String, String> statuses = const {
    'student': 'Student',
    'graduate': 'Fresh graduate',
    'professional': 'Working professional',
  };
  Uint8List? photo;
  bool loaded = false;

  bool get completed => profile['completed'] == true;

  String get name {
    final n = (profile['full_name'] as String?)?.trim();
    if (n != null && n.isNotEmpty) return n;
    final u = FirebaseAuth.instance.currentUser;
    return (u?.displayName?.trim().isNotEmpty ?? false) ? u!.displayName!.trim() : (u?.email ?? '');
  }

  String get firstName => name.split(' ').first;

  String get initials {
    final words = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty && !w.contains('@')).toList();
    if (words.isEmpty) return '?';
    return (words.first[0] + (words.length > 1 ? words.last[0] : '')).toUpperCase();
  }

  /// Degree and university, e.g. "BS Software Engineering · NED University"
  String get subtitle =>
      [profile['degree'], profile['university']].whereType<String>().where((s) => s.isNotEmpty).join(' · ');

  // ---- app settings (Day 24), saved in the account so they follow the user ----
  static const defaultSettings = {'theme': 'system', 'voice': 'female', 'speech_rate': 'normal', 'language': 'en'};

  Map<String, dynamic> get settings => {...defaultSettings, ...?(profile['settings'] as Map?)?.cast<String, dynamic>()};

  String setting(String name) => '${settings[name]}';

  ThemeMode get themeMode => switch (setting('theme')) {
    'dark' => ThemeMode.dark,
    'light' => ThemeMode.light,
    _ => ThemeMode.system,
  };

  /// Change one setting: shown at once, then saved; put back if saving fails.
  Future<void> saveSetting(String name, String value) async {
    final before = settings;
    profile = {
      ...profile,
      'settings': {...before, name: value},
    };
    notifyListeners();
    try {
      final r = await api.put('/profile', {
        'settings': {name: value},
      });
      profile = (r['profile'] as Map).cast<String, dynamic>();
    } catch (_) {
      profile = {...profile, 'settings': before};
      notifyListeners();
      rethrow;
    }
    notifyListeners();
  }

  /// Google's photo, used when no photo was uploaded.
  String? get googlePhotoUrl => FirebaseAuth.instance.currentUser?.photoURL;

  Future<void> load() async {
    final r = await api.get('/profile');
    profile = (r['profile'] as Map).cast<String, dynamic>();
    suggested = (r['suggested'] as Map? ?? {}).cast<String, dynamic>();
    statuses = (r['statuses'] as Map? ?? statuses).cast<String, String>();
    photo = r['has_photo'] == true ? _bytes(await api.getBytes('/profile/photo')) : null;
    loaded = true;
    notifyListeners();
  }

  /// Save some fields. Throws ApiException with fieldErrors when something is wrong.
  Future<void> save(Map<String, dynamic> fields) async {
    final r = await api.put('/profile', fields);
    profile = (r['profile'] as Map).cast<String, dynamic>();
    notifyListeners();
  }

  /// Shrink the picked image to a 256x256 JPEG (about 20-40 KB) on the device, then upload.
  Future<void> uploadPhoto(Uint8List original) async {
    final small = shrinkPhoto(original);
    await api.put('/profile/photo', {'image': base64Encode(small)});
    photo = small;
    notifyListeners();
  }

  Future<void> removePhoto() async {
    await api.delete('/profile/photo');
    photo = null;
    notifyListeners();
  }

  void clear() {
    profile = {};
    suggested = {};
    photo = null;
    loaded = false;
    notifyListeners();
  }

  static Uint8List? _bytes(List<int>? b) => b == null ? null : Uint8List.fromList(b);
}

/// Square-crop the middle of the image and make it 256x256 JPEG. Throws if it isn't an image.
Uint8List shrinkPhoto(Uint8List original, {int size = 256}) {
  final decoded = img.decodeImage(original);
  if (decoded == null) throw const FormatException('That file is not an image we can read.');
  final upright = img.bakeOrientation(decoded); // phone photos store rotation separately
  final square = img.copyResizeCropSquare(upright, size: size, interpolation: img.Interpolation.average);
  return Uint8List.fromList(img.encodeJpg(square, quality: 82));
}

final profileStore = ProfileStore();
