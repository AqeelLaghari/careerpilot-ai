import 'package:careerpilot/services/speaker.dart';
import 'package:careerpilot/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('dark theme switches the whole palette, the logo navy stays', () {
    final light = buildTheme();
    final lightText = AppColors.text;
    final dark = buildTheme(dark: true);
    expect(dark.brightness, Brightness.dark);
    expect(light.brightness, Brightness.light);
    expect(AppColors.dark, isTrue);
    expect(AppColors.text, isNot(lightText));
    expect(AppColors.navy, const Color(0xFF011A42));
    buildTheme(); // back to light for other tests
    expect(AppColors.dark, isFalse);
  });

  test('speaking speed setting', () {
    expect(Speaker.rateFor('slow'), lessThan(Speaker.rateFor('normal')));
    expect(Speaker.rateFor('fast'), greaterThan(Speaker.rateFor('normal')));
  });
}
