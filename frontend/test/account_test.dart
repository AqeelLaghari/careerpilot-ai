import 'dart:typed_data';

import 'package:careerpilot/services/password_rules.dart';
import 'package:careerpilot/services/profile_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

void main() {
  group('password rules', () {
    const name = 'Aqeel Laghari', email = 'aqeel.l@example.com';

    test('a strong password passes every rule', () {
      expect(passwordOk('Blue#River42', name, email), isTrue);
      expect(passwordStrength('Blue#River42xy', name, email), 4);
    });

    test('each missing rule is caught', () {
      expect(passwordOk('Ab1!', name, email), isFalse); // too short
      expect(passwordOk('blue#river42', name, email), isFalse); // no uppercase
      expect(passwordOk('Blue#RiverXY', name, email), isFalse); // no number
      expect(passwordOk('BlueRiver42', name, email), isFalse); // no symbol
      expect(passwordOk('Aqeel#2026x', name, email), isFalse); // contains the name
      expect(passwordOk('Aqeel.l#2026X', 'Someone Else', email), isFalse); // contains the email name
    });

    test('strength grows with the rules met', () {
      expect(passwordStrength('', name, email), 0);
      expect(passwordStrength('abc', name, email), lessThan(passwordStrength('Abcdefg1', name, email)));
      expect(passwordStrength('Blue#Rive42', name, email), 3); // all rules, under 12 characters
    });
  });

  test('photos are cropped to a small square JPEG', () {
    final big = img.Image(width: 1200, height: 800);
    img.fill(big, color: img.ColorRgb8(30, 60, 140));
    final small = shrinkPhoto(Uint8List.fromList(img.encodePng(big)));
    final back = img.decodeJpg(small)!;
    expect([back.width, back.height], [256, 256]);
    expect(small.length, lessThan(40 * 1024));
    expect(() => shrinkPhoto(Uint8List.fromList([1, 2, 3])), throwsFormatException);
  });
}
