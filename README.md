# Klar Assist Extensions

Ein zusätzlicher modularer Home-Assistant-Conversation-Agent mit deterministischen deutschen Wetterantworten. Nicht zuständige Anfragen werden an den konfigurierten offiziellen Klar-Agent weitergeleitet. Domain: `klar_assist_extensions`, Version 0.2.0.

**Voraussetzung:** Die [offizielle Klar-NLU-Home-Assistant-Integration](https://github.com/FABBricate-IT-Solutions/klar-ha-nlu) muss separat installiert und konfiguriert sein. Ihr Conversation-Agent muss verfügbar sein. Diese Extension verändert oder patcht weder Klar-Dateien noch den Klar-Docker-Container. Beide Projekte bleiben unabhängig aktualisierbar.

## Funktionsumfang

- Aktuelles Wetter, heute, morgen, übermorgen und zukünftige Wochentage.
- „In drei Tagen“ und „die nächsten fünf Tage“; maximal sieben Tage voraus beziehungsweise acht Tage insgesamt, zusätzlich begrenzt durch vorhandene Forecastdaten.
- Tagesantwort mit Zustand, Min/Max, Regenwahrscheinlichkeit, Niederschlagsmenge, Luftfeuchtigkeit und natürlicher Bewölkungs-/Windbeschreibung. Fehlende Werte werden ausgelassen; echte Nullwerte bleiben erhalten.
- Kompakte Mehrtagesantworten und spezifische Regenantworten.
- Nicht-Wetteranfragen werden unverändert an Klar delegiert. Ein deaktiviertes Weather-Modul bedeutet vollständige Delegation.

Deutsch ist die einzige aktiv unterstützte Weather-Sprache. Regionale Varianten wie de-DE und de-AT werden normalisiert. Englisch ist strukturell vorbereitet, aber nicht aktiviert. Nicht unterstützte Sprachen werden mit ihrer ursprünglichen Sprache und ihrem Benutzercontext an Klar weitergereicht; deutsche Wetterregeln greifen dann nicht.

## Architektur und Klar-Abhängigkeit

Assist → Klar Assist Extensions → aktivierte Module → sonst offizieller Klar-Agent.

Die Conversation-Schicht und Modulschnittstelle sind sprachneutral. Weather besitzt einen engen Kandidatenfilter; Nicht-Wetteranfragen erzeugen keinen zusätzlichen Parse-Aufruf durch die Extension. Wetterkandidaten verwenden Klars öffentliche v2-Parse-API (Schema 2.0) zur Erkennung und Entity-Bindung. Zeitinterpretation, datierte Forecastauswahl und Antwortformatierung erfolgen im Weather-Modul.

**Wetter bleibt von der Klar-NLU-Engine abhängig.** Der Klar-Conversation-Agent verarbeitet übernommene Wetterfragen nicht, der Klar-Dienst erhält dafür jedoch weiterhin einen Parse-Aufruf. Weather verwendet kein LLM, Chat-Fallback, Refine oder Rust-Ausführungsrenderer. Erkannte Wetterkandidaten mit fehlenden Daten erhalten eine deterministische Fehlerantwort. Für delegierte Anfragen gilt Klars normales Verhalten.

Ein späteres Calendar-Modul kann über dieselbe Modulverwaltung ergänzt werden; derzeit ist kein Calendar-Modul implementiert. Kalenderfragen werden delegiert.

## Voraussetzungen

- Home Assistant mindestens 2026.10.1; Python entsprechend der HA-Version.
- Separat installierte und konfigurierte offizielle Klar-NLU-Integration. Getestet mit Version 2026.10.3 und Parse-Schema 2.0.
- Erreichbare HTTP(S)-API-Origin des bestehenden Klar-Dienstes, bei geschützter API dessen Token.
- Mindestens eine verfügbare Wetterentity, die für Assist/Conversation freigegeben ist. Kein bestimmter Wetteranbieter ist fest codiert.
- Daily-Forecasts für Tagesfragen.

## Installation und Einrichtung

Bestätigtes Veröffentlichungsziel: [marco-taylor/klar-assist-extensions](https://github.com/marco-taylor/klar-assist-extensions). Codeowner: @marco-taylor. [Issues](https://github.com/marco-taylor/klar-assist-extensions/issues). Das Repository wird erst nach ausdrücklicher Freigabe erstellt; diese Links sind daher vor der Ersterstellung noch nicht erreichbar.

Nach Veröffentlichung kann `https://github.com/marco-taylor/klar-assist-extensions` in HACS als **Integration / Custom Repository** hinzugefügt werden. HACS installiert ausschließlich den eigenen Domainordner. Nach der regulären HA-Erkennung unter Einstellungen → Geräte & Dienste die Integration **Klar Assist Extensions** hinzufügen.

Konfigurierbar sind:

| Option | Bedeutung |
|---|---|
| Offizieller Klar-Agent | Explizites Delegationsziel, zum Beispiel `conversation.klar_nlu` |
| Klar-API-URL | HTTP(S)-Origin ohne Benutzerinfo, Pfad oder Query |
| Klar-API-Token | Optionaler bestehender Token, falls die API ihn benötigt |
| Weather aktivieren | Aktiviert die lokale Weather-Verarbeitung |

Ein neuer ConfigEntry übernimmt **keinen Token automatisch** aus einer anderen Integration. Der Benutzer gibt ihn im Formular ein. HA speichert ihn als ConfigEntry-Datum und zeigt den gespeicherten Wert beim erneuten Öffnen der Optionen als Passwortfeld-Vorgabe. Der Token ist nicht Bestandteil dieses Repositorys. Die Extension erzeugt keinen Klar-Token.

Die Einrichtung erzeugt einen zusätzlichen Conversation-Agent und ändert keine vorhandene Assist-Pipeline oder Standardagent-Auswahl. Die spätere Auswahl erfolgt ausdrücklich durch den Benutzer. Eine Optionsänderung lädt nur diese Extension neu. Bei deaktiviertem Weather ist keine Parse-API-URL erforderlich.

## Berechtigungen und Context

Weather prüft vor dem Statezugriff sowohl Assist-Freigabe als auch Entity-Leserecht. Forecast-Serviceaufrufe behalten den ursprünglichen Benutzercontext; HAs zusätzliche Serviceberechtigungen bleiben aktiv. Fehlende Rechte werden nicht durch einen privilegierten Fallback umgangen.

In der getesteten HA-Version 2026.10.1 benötigt `weather.get_forecasts` zusätzlich Entity-Steuerrechte. Reine Lesebenutzer können freigegebenes aktuelles Wetter lesen, erhalten bei Tagesforecasts eine deterministische Nichtverfügbarkeitsantwort. Unbekannte oder inaktive Benutzer werden abgewiesen.

Delegation erhält Text, Sprache, Context, Gesprächs-ID und die von HA unterstützten Geräte-/Satelliteninformationen. Der Ziel-Agent ist selbst für seine Rechteprüfung verantwortlich. Klar kann die regionale Antwortsprache etwa von de-DE auf de normalisieren; die Extension gibt seine Antwort unverändert zurück. Systemcontexts von HA bleiben erhalten, werden aber niemals als Ersatz für abgewiesene Benutzer erzeugt.

## Validierung

Das öffentliche Repository enthält ausschließlich die Integration, Installationsdokumentation und Veröffentlichungsmetadaten. Isolierte Tests und Entwicklungswerkzeuge werden separat aufbewahrt. Die GitHub-Workflows prüfen die Integration mit offiziellem hassfest und der HACS Action.

## Entfernen und Rollback

Zuerst eine eventuell ausdrücklich ausgewählte Pipeline wieder auf ihren früheren Agent setzen. Unter Geräte & Dienste ausschließlich den ConfigEntry von Klar Assist Extensions entfernen. Klar und dessen ConfigEntry bleiben erhalten. Erst nach Entladen den eigenen Domainordner entfernen. Eine ältere Extension-Version lässt sich über eine zuvor gesicherte Version wiederherstellen; deren Laufzeitübernahme nach HAs regulärem Verfahren durchführen. Tokens und komplette HA-Speicherdateien nicht pauschal über eine laufende Installation kopieren.

## Lizenz und Herkunft

MIT; siehe [klar-assist-extensions/LICENSE](LICENSE). Wiederverwendete Klar-Wetterformatter-/Referenzteile behalten die Copyright-Hinweise des ursprünglichen MIT-Projekts; Details in [klar-assist-extensions/THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
