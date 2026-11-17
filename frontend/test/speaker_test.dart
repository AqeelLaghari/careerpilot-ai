import 'package:careerpilot/services/speaker.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // The voices Chrome on Windows and Edge report (Day 27: Urdu interviews)
  final chrome = <Map>[
    {'name': 'Google US English', 'locale': 'en-US'},
    {'name': 'Microsoft David - English (United States)', 'locale': 'en-US'},
    {'name': 'Google हिन्दी', 'locale': 'hi-IN'},
  ];
  final edge = <Map>[
    {'name': 'Microsoft Uzma Online (Natural) - Urdu (Pakistan)', 'locale': 'ur-PK'},
    {'name': 'Microsoft Asad Online (Natural) - Urdu (Pakistan)', 'locale': 'ur-PK'},
    {'name': 'Microsoft Swara Online (Natural) - Hindi (India)', 'locale': 'hi-IN'},
  ];

  test('an Urdu voice of the chosen type is picked when there is one', () {
    expect(Speaker.bestVoice(edge, 'ur', wantMale: false)?['name'], contains('Uzma'));
    expect(Speaker.bestVoice(edge, 'ur', wantMale: true)?['name'], contains('Asad'));
  });

  test('Chrome has no Urdu voice: the Hindi voice is the fallback', () {
    expect(Speaker.bestVoice(chrome, 'ur', wantMale: false), isNull);
    expect(Speaker.bestVoice(chrome, 'hi', wantMale: false)?['name'], 'Google हिन्दी');
    expect(Speaker.bestVoice(chrome, 'en', wantMale: true)?['name'], contains('David'));
  });
}
