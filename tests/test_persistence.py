"""Fallos inyectados de transporte/VM, solo bytes sintéticos; nunca GPU ni imágenes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import persistencia_colab as storage
import entrenar_165_wsl as client


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(storage, 'STORE', self.root / 'drive')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_tls_response_lost_then_reconnect_skips_committed_part(self):
        archive = self.root / 'archive.zip'
        archive.write_bytes(b'synthetic-backup' * 100)
        manifest = client.transport_manifest(archive)
        incoming = self.root / 'incoming'
        incoming.write_bytes(archive.read_bytes())
        storage.accept_part(manifest, 0, incoming)
        # Respuesta perdida; la siguiente conexión debe consultar SHA, sin incoming.
        self.assertFalse(incoming.exists())
        self.assertTrue(storage.valid_part(manifest, 0))
        storage.accept_part(manifest, 0, incoming)
        target = storage.finish_archive(manifest)
        self.assertEqual(storage.sha256(target), manifest['sha256'])
        self.assertEqual(target, storage.finish_archive(manifest))

    def test_corrupt_part_never_publishes_archive(self):
        archive = self.root / 'archive.zip'
        archive.write_bytes(b'expected')
        manifest = client.transport_manifest(archive)
        incoming = self.root / 'incoming'
        incoming.write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError, 'corrupto'):
            storage.accept_part(manifest, 0, incoming)
        with self.assertRaisesRegex(RuntimeError, 'ausente'):
            storage.finish_archive(manifest)
        self.assertFalse(storage.archive_valid(manifest))

    def test_multi_part_assembly_and_changed_runtime(self):
        archive = self.root / 'archive.zip'
        archive.write_bytes(b'abcdefghijk')
        with patch.object(client, 'PART_SIZE', 3):
            manifest = client.transport_manifest(archive)
        for index, part in enumerate(manifest['parts']):
            incoming = self.root / 'incoming'
            start = index * 3
            incoming.write_bytes(archive.read_bytes()[start:start+part['size']])
            storage.accept_part(manifest, index, incoming)
        # Nueva VM sin staging: todos los fragmentos ya están en Drive.
        self.assertTrue(all(storage.valid_part(manifest, i) for i in range(4)))
        self.assertEqual(storage.finish_archive(manifest).read_bytes(), archive.read_bytes())

    def commit(self, epoch):
        local = self.root / 'old-content'
        local.mkdir(exist_ok=True)
        (local / 'checkpoint.pt').write_bytes(f'optimizer/scheduler epoch {epoch}'.encode())
        (local / 'results.csv').write_text(f'epoch,loss\n{epoch},0.1\n')
        return storage.commit_snapshot(self.root / 'run', local,
            ['checkpoint.pt', 'results.csv'], dict(epoch=epoch, run_id='test', dataset_sha256='a'*64))

    def test_vm_loss_restores_last_valid_generation_without_reset(self):
        previous = self.commit(37)
        corrupt = self.commit(38)
        (corrupt / 'checkpoint.pt').write_bytes(b'truncated')
        incomplete = self.root / 'run/checkpoints/039-interrupted'
        incomplete.mkdir()
        (incomplete / 'checkpoint.pt').write_bytes(b'not-committed')
        fresh = self.root / 'new-content'
        restored = storage.restore_snapshot(self.root / 'run', fresh, 'a'*64)
        self.assertEqual(restored['epoch'], 37)
        self.assertEqual((fresh / 'checkpoint.pt').read_bytes(), (previous / 'checkpoint.pt').read_bytes())

    def test_all_checkpoints_corrupt_or_wrong_dataset_fail_closed(self):
        generation = self.commit(42)
        with self.assertRaisesRegex(RuntimeError, 'ninguno es válido'):
            storage.latest_snapshot(self.root / 'run', 'b'*64)
        (generation / 'checkpoint.pt').unlink()
        with self.assertRaisesRegex(RuntimeError, 'no reiniciar'):
            storage.latest_snapshot(self.root / 'run', 'a'*64)

    def test_new_runtime_cannot_steal_owner_by_age(self):
        run = self.root / 'run'
        run.mkdir()
        with patch.object(storage, 'boot_id', return_value='old-boot'):
            storage.claim_owner(run)
        with patch.object(storage, 'boot_id', return_value='new-boot'):
            with self.assertRaisesRegex(RuntimeError, '--recover-boot old-boot'):
                storage.claim_owner(run)
            owner = storage.claim_owner(run, 'old-boot')
            self.assertEqual(owner['boot_id'], 'new-boot')

    def test_backoff_bounded_and_permanent_failure_not_retried(self):
        calls, delays = [], []
        def failed():
            calls.append(1)
            raise client.TransportError('DNS')
        with self.assertRaises(client.TransportError):
            client.retry_read(failed, sleep=delays.append)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(delays), 3)
        def permanent():
            raise RuntimeError('401')
        with self.assertRaises(RuntimeError):
            client.retry_read(permanent, sleep=lambda _: self.fail('Permanent error retried'))

    def test_remote_protocol_executes_library_in_fresh_process_and_reports_errors(self):
        def execute(*args):
            filename = args[args.index('-f') + 1]
            process = subprocess.run([sys.executable, filename], capture_output=True, text=True, check=True)
            return process.stdout
        with patch.object(client, 'cli', side_effect=execute):
            result = client.remote('from persistencia_colab import boot_id\nresult = {"boot": boot_id(), "gpu": False}')
            self.assertFalse(result['gpu'])
            self.assertTrue(result['boot'])
            with self.assertRaisesRegex(RuntimeError, 'Drive necesita autorización'):
                client.remote('raise RuntimeError("Drive necesita autorización")')

    def test_only_smoke_valid_does_not_reset_prior_training(self):
        self.commit(0)
        corrupt = self.commit(10)
        (corrupt / 'checkpoint.pt').write_bytes(b'truncated')
        with self.assertRaisesRegex(RuntimeError, 'no reiniciar 100'):
            storage.latest_snapshot(self.root / 'run', 'a'*64)

    def test_controller_start_twice_launches_one_worker(self):
        from unittest.mock import Mock
        spec = importlib.util.spec_from_file_location('controller_test', SCRIPTS / 'control_entrenamiento_colab.py')
        control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control)
        content = self.root / 'content'
        root = content / 'ecoguard-entrenamiento'
        root.mkdir(parents=True)
        training = content / 'entrenar_colab.py'
        training.write_text('import time; time.sleep(15)')
        storage.atomic_json(root / 'deployment.json', {'entrenar_colab.py': storage.sha256(training)})
        archive_bytes = b'synthetic archive'
        import hashlib
        digest = hashlib.sha256(archive_bytes).hexdigest()
        dataset = storage.STORE / 'datasets' / digest
        dataset.mkdir(parents=True)
        (dataset / 'ecoguard-validacion.zip').write_bytes(archive_bytes)
        (dataset / 'arquitectura-validada.json').write_text('{}')
        processes = []
        real_popen = subprocess.Popen
        def spawn(args, **kwargs):
            args = [args[0], '-u', str(training)]
            kwargs['cwd'] = str(content)
            process = real_popen(args, **kwargs)
            processes.append(process)
            return process
        def path(value):
            value = str(value)
            if value == '/content' or value.startswith('/content/'):
                return content / value.removeprefix('/content').lstrip('/')
            return Path(value)
        try:
            with patch.object(control, 'Path', side_effect=path), \
                 patch.object(storage, 'require_drive', return_value=storage.STORE), \
                 patch('importlib.util.find_spec', return_value=object()), \
                 patch.dict('os.environ', {'ECOGUARD_ACTION': 'start', 'ECOGUARD_DATASET_SHA256': digest}), \
                 patch('subprocess.Popen', side_effect=spawn):
                self.assertTrue(control.main()['vivo'])
                self.assertTrue(control.main()['vivo'])
            self.assertEqual(len(processes), 1)
        finally:
            for process in processes:
                process.terminate()
                process.wait(timeout=5)

    def test_ambiguous_start_queries_status_without_second_start(self):
        manifest = dict(sha256='a'*64, size=1, parts=[{}])
        with patch.object(sys, 'argv', ['client', 'start']), \
             patch.object(client, 'transport_manifest', return_value=manifest), \
             patch.object(client, 'remote', return_value=True), \
             patch.object(client, 'install_code'), \
             patch.object(client, 'status', side_effect=[{'vivo': False},
                 client.TransportError('TLS EOF'), {'vivo': True}]) as status:
            client.main()
        self.assertEqual(sum(call.args[1:] == ('start', None) for call in status.call_args_list), 1)
        self.assertEqual(status.call_count, 3)

    def test_worker_lock_survives_controller_disconnect_and_prevents_duplicates(self):
        import fcntl
        lockpath = self.root / 'worker.lock'
        lock = lockpath.open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready = self.root / 'ready'
        script = ('import pathlib,sys,time; '
                  'pathlib.Path(sys.argv[1]).touch(); time.sleep(15)')
        worker = subprocess.Popen([sys.executable, '-c', script, str(ready)],
                                  pass_fds=(lock.fileno(),), start_new_session=True,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        try:
            lock.close()  # Simular desconexión del controlador WSL.
            import time
            for _ in range(100):
                if ready.exists():
                    break
                time.sleep(.01)
            self.assertTrue(ready.exists())
            with lockpath.open('a') as second:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertIsNone(worker.poll())
        finally:
            worker.terminate()
            worker.wait(timeout=5)
        with lockpath.open('a') as restarted:
            fcntl.flock(restarted, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == '__main__':
    unittest.main(verbosity=2)
