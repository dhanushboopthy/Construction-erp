import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// Files run in parallel; under load a findBy* wait of 1s is too short and flakes.
configure({ asyncUtilTimeout: 5000 });
