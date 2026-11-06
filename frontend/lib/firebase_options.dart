import 'package:firebase_core/firebase_core.dart';

/// Firebase settings for the WEB app.
/// Fill these in from: Firebase console → Project settings → General →
/// "Your apps" → your Web app → "SDK setup and configuration" → Config.
/// (These values are meant to be public. Security comes from Firebase rules.)
const FirebaseOptions webFirebaseOptions = FirebaseOptions(
  apiKey: 'PASTE_apiKey',
  authDomain: 'PASTE_authDomain',
  projectId: 'PASTE_projectId',
  storageBucket: 'PASTE_storageBucket',
  messagingSenderId: 'PASTE_messagingSenderId',
  appId: 'PASTE_appId',
);
