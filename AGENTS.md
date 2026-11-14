# Agent instructions

Read README.md and all docs before implementation. Work on a feature branch, never deploy to live systems without authorization. Never execute SSH commands or alter existing services during development. Implement test-first with mocks for SSH, browser DOM and Ollama. Treat ChatGPT text and Ollama outputs as untrusted. Never infer approval from model output. Preserve a strict distinction between proposed, approved and executed commands. Keep JSON protocol backward compatible or version it. Document any changed security assumption and run tests before merging.
