import 'package:flutter/material.dart';

import '../services/profile_store.dart';
import '../theme.dart';

/// The user's round picture: the uploaded photo, else their Google photo, else their
/// initials on a coloured circle. Updates by itself when the profile changes.
class UserAvatar extends StatelessWidget {
  const UserAvatar({super.key, this.radius = 18});
  final double radius;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: profileStore,
      builder: (context, _) {
        final photo = profileStore.photo;
        final google = profileStore.googlePhotoUrl;
        final initials = CircleAvatar(
          radius: radius,
          backgroundColor: _colourFor(profileStore.name),
          child: Text(
            profileStore.initials,
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: radius * 0.8),
          ),
        );
        if (photo != null) return CircleAvatar(radius: radius, backgroundImage: MemoryImage(photo));
        if (google == null) return initials;
        return ClipOval(
          child: Image.network(
            google,
            width: radius * 2,
            height: radius * 2,
            fit: BoxFit.cover,
            // Google's photo server may block the browser's canvas; show it as a normal <img> then
            webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
            errorBuilder: (_, _, _) => initials,
          ),
        );
      },
    );
  }

  /// A stable colour per name, so the same person always gets the same circle.
  static Color _colourFor(String name) {
    const colours = [AppColors.brand, Color(0xFF0E7490), Color(0xFF7C3AED), Color(0xFFBE185D), Color(0xFF15803D)];
    return colours[name.codeUnits.fold(0, (a, b) => a + b) % colours.length];
  }
}
