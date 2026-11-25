import unittest

from simulation import BLOCKED, HEIGHT, WIDTH, Simulation, space_time_path


class RoutingTests(unittest.TestCase):
    def test_path_stays_in_bounds_and_avoids_racks(self) -> None:
        path = space_time_path((1, 1), (16, 1), set())
        self.assertTrue(path)
        self.assertEqual(path[0], (1, 1))
        self.assertEqual(path[-1], (16, 1))
        for x, y in path:
            self.assertGreaterEqual(x, 0)
            self.assertLess(x, WIDTH)
            self.assertGreaterEqual(y, 0)
            self.assertLess(y, HEIGHT)
            self.assertNotIn((x, y), BLOCKED)

    def test_time_reservations_cause_a_detour(self) -> None:
        reservations = {(2, 1, 1), (2, 1, 2), (2, 1, 3)}
        path = space_time_path((1, 1), (3, 1), reservations)
        self.assertTrue(path)
        self.assertEqual(path[-1], (3, 1))
        self.assertNotEqual(path[1], (2, 1))


class SimulationTests(unittest.TestCase):
    def test_controls_change_authoritative_state(self) -> None:
        simulation = Simulation()
        self.assertFalse(simulation.snapshot()["running"])
        simulation.start()
        self.assertTrue(simulation.snapshot()["running"])
        simulation.step()
        self.assertEqual(simulation.snapshot()["tick"], 1)
        simulation.pause()
        self.assertFalse(simulation.snapshot()["running"])
        simulation.reset()
        self.assertEqual(simulation.snapshot()["tick"], 0)
        self.assertEqual(len(simulation.snapshot()["robots"]), 3)


if __name__ == "__main__":
    unittest.main()
