import 'package:careerpilot/config.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('accepts https and http server addresses, without a trailing slash', () {
    expect(serverUrlFrom(' https://api.example.com/ '), 'https://api.example.com');
    expect(serverUrlFrom('http://192.168.1.5:8000'), 'http://192.168.1.5:8000');
  });

  test('rejects anything that is not a server address', () {
    expect(serverUrlFrom(''), isNull);
    expect(serverUrlFrom('ftp://example.com'), isNull);
    expect(serverUrlFrom('not a url'), isNull);
    expect(serverUrlFrom('https://'), isNull);
  });

  test('laptop builds keep the built-in address (no config file to read)', () async {
    final before = apiBaseUrl;
    await loadServerConfig();
    expect(apiBaseUrl, before);
  });
}
