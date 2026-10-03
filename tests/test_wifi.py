"""Aggiornamento delle credenziali Wi-Fi (`python -m dash --wifi`): niente comandi veri."""
from __future__ import annotations

import contextlib
import io
import logging
import unittest
from typing import Any

from dash import wifi
from dash.main import aggiorna_wifi, parse_args

PASSWORD = "Segreta-Davvero-42"
RETI = "Ospiti-FASTWEB:2412 MHz:100:WPA2 WPA3\nAltra\\:rete:5180 MHz:60:WPA2\nCasa:5745 MHz:50:WPA2\nCasa:2437 MHz:40:WPA2\n"


class NmcliFinto:
    """Risponde come nmcli e ricorda i comandi; `profili` è l'elenco `NAME:TYPE` che dice di avere."""

    def __init__(self, profili: str = "Wired connection 1:802-3-ethernet\nlo:loopback\n", reti: str = RETI,
                 fallisce: dict[str, tuple[int, str]] | None = None) -> None:
        self.comandi: list[list[str]] = []
        self.profili, self.reti, self.fallisce = profili, reti, fallisce or {}

    def __call__(self, cmd: list[str]) -> tuple[int, str]:
        self.comandi.append(cmd)
        testo = " ".join(cmd)
        for parte, risposta in self.fallisce.items():
            if parte in testo:
                return risposta
        if "wifi list" in testo:
            return 0, self.reti
        if "DEVICE,TYPE" in testo:
            return 0, "eth0:ethernet\nwlan0:wifi\np2p-dev-wlan0:wifi-p2p\nlo:loopback"
        if "NAME,TYPE" in testo:
            return 0, self.profili
        if "IP4.ADDRESS" in testo:
            return 0, "192.168.1.88/24"
        return 0, ""

    def scritti(self) -> list[list[str]]:
        """I comandi che cambiano qualcosa."""
        return [c for c in self.comandi if any(p in c for p in ("add", "modify", "up"))]


class TestValidazione(unittest.TestCase):
    def test_accepts_real_credentials(self) -> None:
        wifi.valida("Ospiti-FASTWEB", PASSWORD)
        wifi.valida("Rete con spazi dentro", "12345678")
        wifi.valida("Caffè ☕", "a" * 63)
        wifi.valida("x" * 32, "f" * 64)                   # 64 cifre esadecimali: chiave già calcolata

    def test_refuses_what_the_network_would_refuse(self) -> None:
        for ssid, password in (("", PASSWORD), ("  ", PASSWORD), (" Rete", PASSWORD), ("x" * 33, PASSWORD),
                               ("è" * 17, PASSWORD),      # 34 byte
                               ("Rete", "corta"), ("Rete", "g" * 64), ("Rete", "a" * 12 + "\n" + "b" * 12),
                               ("Rete", "")):
            with self.assertRaises(wifi.WifiError, msg=(ssid, len(password))):
                wifi.valida(ssid, password)

    def test_errors_never_contain_the_password(self) -> None:
        with self.assertRaises(wifi.WifiError) as e:
            wifi.valida("Rete", "x" * 5)
        self.assertNotIn("xxxxx", str(e.exception))


class TestAggiorna(unittest.TestCase):
    def test_creates_the_profile_when_missing(self) -> None:
        nm = NmcliFinto()
        ip = wifi.aggiorna("Ospiti-FASTWEB", PASSWORD, nm, root=True)
        self.assertEqual(ip, "192.168.1.88")
        add, up = nm.scritti()
        self.assertEqual(add[:7], ["nmcli", "connection", "add", "type", "wifi", "ifname", "wlan0"])
        self.assertIn("wpa-psk", add)                       # WPA2: il Pi 3 non gestisce bene il WPA3
        self.assertEqual(add[add.index("wifi-sec.psk") + 1], PASSWORD)
        self.assertEqual(add[add.index("connection.autoconnect") + 1], "yes")
        self.assertEqual(up, ["nmcli", "connection", "up", "id", "Ospiti-FASTWEB"])

    def test_updates_the_existing_profile_instead_of_duplicating_it(self) -> None:
        nm = NmcliFinto("Ospiti-FASTWEB:802-11-wireless\nWired connection 1:802-3-ethernet\n")
        wifi.aggiorna("Ospiti-FASTWEB", PASSWORD, nm, root=True)
        modifica = nm.scritti()[0]
        self.assertEqual(modifica[:5], ["nmcli", "connection", "modify", "id", "Ospiti-FASTWEB"])
        self.assertFalse(any("add" in c[:3] for c in nm.comandi))

    def test_a_profile_of_another_kind_with_the_same_name_is_not_reused(self) -> None:
        nm = NmcliFinto("Ospiti-FASTWEB:vpn\n")
        wifi.aggiorna("Ospiti-FASTWEB", PASSWORD, nm, root=True)
        self.assertIn("add", nm.scritti()[0])

    def test_sudo_only_when_not_root_and_only_for_changes(self) -> None:
        nm = NmcliFinto()
        wifi.aggiorna("Rete", PASSWORD, nm, root=False)
        for c in nm.scritti():
            self.assertEqual(c[0], "sudo")
        self.assertTrue(all(c[0] == "nmcli" for c in nm.comandi if c not in nm.scritti()))
        nm = NmcliFinto()
        wifi.aggiorna("Rete", PASSWORD, nm, root=True)
        self.assertTrue(all(c[0] == "nmcli" for c in nm.comandi))

    def test_ssid_that_looks_like_an_option_is_a_value(self) -> None:
        nm = NmcliFinto()
        wifi.aggiorna("-pericolosa", PASSWORD, nm, root=True)
        self.assertEqual(nm.scritti()[-1], ["nmcli", "connection", "up", "id", "-pericolosa"])

    def test_failed_connection_keeps_the_profile_and_hides_the_password(self) -> None:
        nm = NmcliFinto(fallisce={"connection up": (4, f"Error: Connection activation failed: {PASSWORD} rifiutata")})
        with self.assertRaises(wifi.WifiError) as e:
            wifi.aggiorna("Rete", PASSWORD, nm, root=True)
        self.assertIn("credenziali salvate ma collegamento non riuscito", str(e.exception))
        self.assertNotIn(PASSWORD, str(e.exception))
        self.assertEqual(len(nm.scritti()), 2)               # il profilo era già stato scritto

    def test_failed_save_hides_the_password_and_does_not_connect(self) -> None:
        nm = NmcliFinto(fallisce={"connection add": (1, f"Error: property psk {PASSWORD} is invalid")})
        with self.assertRaises(wifi.WifiError) as e:
            wifi.aggiorna("Rete", PASSWORD, nm, root=True)
        self.assertNotIn(PASSWORD, str(e.exception))
        self.assertTrue(str(e.exception).startswith("profilo non salvato"))
        self.assertFalse(any("up" in c for c in nm.comandi))

    def test_invalid_credentials_touch_nothing(self) -> None:
        nm = NmcliFinto()
        with self.assertRaises(wifi.WifiError):
            wifi.aggiorna("Rete", "corta", nm, root=True)
        self.assertEqual(nm.comandi, [])

    def test_no_wifi_interface(self) -> None:
        nm = NmcliFinto(fallisce={"DEVICE,TYPE": (0, "eth0:ethernet\nlo:loopback")})
        with self.assertRaises(wifi.WifiError) as e:
            wifi.aggiorna("Rete", PASSWORD, nm, root=True)
        self.assertIn("nessuna interfaccia Wi-Fi", str(e.exception))


class TestReti(unittest.TestCase):
    def test_networks_are_parsed_with_escaped_colons(self) -> None:
        elenco = wifi.reti(NmcliFinto())
        self.assertEqual([r[0] for r in elenco], ["Ospiti-FASTWEB", "Altra:rete", "Casa", "Casa"])
        self.assertEqual(elenco[0], ("Ospiti-FASTWEB", 2412, 100, "WPA2 WPA3"))

    def test_warnings_for_missing_and_5ghz_only_networks(self) -> None:
        elenco = wifi.reti(NmcliFinto())
        self.assertEqual(wifi.avvisi("Ospiti-FASTWEB", elenco), [])
        self.assertEqual(wifi.avvisi("Casa", elenco), [])              # una delle due è a 2,4 GHz
        self.assertIn("solo a 5 GHz", wifi.avvisi("Altra:rete", elenco)[0])
        self.assertIn("non si vede", wifi.avvisi("ospiti-fastweb", elenco)[0])   # maiuscole diverse

    def test_scan_failure_is_reported(self) -> None:
        with self.assertRaises(wifi.WifiError):
            wifi.reti(NmcliFinto(fallisce={"wifi list": (1, "Error: Wi-Fi is disabled")}))


class TestComando(unittest.TestCase):
    def _lancia(self, ssid: str, nm: NmcliFinto, ssid_chiesto: str = "", segreti: tuple[str, ...] = (PASSWORD, PASSWORD)) -> tuple[int, str, Any]:
        domande: list[str] = []
        it = iter(segreti)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            codice = aggiorna_wifi(ssid, chiedi=lambda p: domande.append(p) or ssid_chiesto,
                                   chiedi_segreto=lambda p: domande.append(p) or next(it),
                                   esegui=nm, root=True)
        return codice, out.getvalue(), domande

    def test_flag_is_parsed(self) -> None:
        self.assertIsNone(parse_args([]).wifi)
        self.assertEqual(parse_args(["--wifi"]).wifi, "")
        self.assertEqual(parse_args(["--wifi", "Casa"]).wifi, "Casa")

    def test_asks_for_the_ssid_and_lists_the_networks(self) -> None:
        codice, testo, domande = self._lancia("", NmcliFinto(), "Ospiti-FASTWEB")
        self.assertEqual(codice, 0)
        self.assertIn("Ospiti-FASTWEB  (2,4 GHz, segnale 100, WPA2 WPA3)", testo)
        self.assertIn("Altra:rete  (5 GHz", testo)
        self.assertEqual(testo.count("Casa  ("), 1)                     # le reti doppie si elencano una volta
        self.assertIn("collegato a «Ospiti-FASTWEB», indirizzo 192.168.1.88", testo)
        self.assertEqual(domande[0], "SSID (nome della rete): ")
        self.assertNotIn(PASSWORD, testo)                                # mai a video

    def test_ssid_on_the_command_line_is_not_asked(self) -> None:
        codice, _, domande = self._lancia("Ospiti-FASTWEB", NmcliFinto())
        self.assertEqual(codice, 0)
        self.assertFalse(any("SSID" in d for d in domande))

    def test_password_asked_twice_and_must_match(self) -> None:
        nm = NmcliFinto()
        codice, testo, _ = self._lancia("Rete", nm, segreti=(PASSWORD, PASSWORD + "x"))
        self.assertEqual(codice, 5)
        self.assertIn("non coincidono", testo)
        self.assertEqual(nm.scritti(), [])                               # niente è cambiato

    def test_warns_about_a_5ghz_network_but_still_saves(self) -> None:
        codice, testo, _ = self._lancia("Altra:rete", NmcliFinto())
        self.assertEqual(codice, 0)
        self.assertIn("attenzione:", testo)
        self.assertIn("solo a 5 GHz", testo)

    def test_errors_are_logged_without_the_password(self) -> None:
        nm = NmcliFinto(fallisce={"connection up": (4, f"Error: {PASSWORD} no")})
        with self.assertLogs("dash", level=logging.ERROR) as log:
            codice, testo, _ = self._lancia("Rete", nm)
        self.assertEqual(codice, 5)
        self.assertNotIn(PASSWORD, "\n".join(log.output) + testo)

    def test_works_when_the_scan_fails(self) -> None:
        nm = NmcliFinto(fallisce={"wifi list": (1, "Error: scan failed")})
        codice, testo, _ = self._lancia("Rete", nm)
        self.assertEqual(codice, 0)

    def test_command_runs_before_the_config_is_loaded(self) -> None:
        """Con una configurazione rotta il Pi deve poter comunque recuperare il Wi-Fi."""
        import tempfile
        from pathlib import Path
        from unittest import mock

        from dash import main as principale
        with tempfile.TemporaryDirectory() as tmp:
            rotta = Path(tmp) / "config.json"
            rotta.write_text("{ non è json", encoding="utf-8")
            with mock.patch.object(principale, "aggiorna_wifi", return_value=0) as m:
                self.assertEqual(principale.main(["-c", str(rotta), "--wifi", "Casa"]), 0)
            m.assert_called_once_with("Casa")


if __name__ == "__main__":
    unittest.main()
