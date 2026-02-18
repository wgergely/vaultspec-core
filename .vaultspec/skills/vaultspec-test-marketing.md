# Marketing Audit

Begin a comprehensive audit of the project as the marketing lead. The goal is to assess the maturity and release readiness of the project base on these aspects:

- **Packaging and Distribution**: Evaluate the current state of packaging and distribution. Does it exist? Is there clear CI/CD pipeline for releases? Are there any issues with the current packaging and distribution process that could hinder the project's ability to reach a wider audience? What dependencies does the project have? Do we provide an installer? Is there a docker image? Is there a clear release process? Are there any blockers to releasing the project to the public?

## Marketing Materials

THe audit will include an assessement of the marketability and positioning of the project. The audit must address:

- **Competitors/Alternatives**: Identify and analyze competitors or alternative solutions in the market. This includes evaluating their strengths and weaknesses, as well as how our project differentiates itself from them. What are the unique selling points of our project? How does it compare to existing solutions in terms of features, performance, and user experience?
- **Feature Gap Analysis**: Identify any gaps in the project's features compared to competitors or user expectations. This includes evaluating the current feature set and identifying any missing features that could enhance the project's value proposition. Are there any critical features that are currently missing? How do these gaps impact the overall user experience and marketability of the project?

## Team Composition

- **ResearchSupervisor**: This Opus agent supervises the team in read-only mode. The Supervisor's role is to oversee the research process. It will read the individual research agent reports and identify poltential gaps, or request more work from the research agents if necessary.
- **ResearchAgent1-3**: These Sonnet agents are responsible for conducting the online research tasks. BOth team lead and ResearchSupervisor can request work and reports.
- **MarketingSupervisor**: This Opus agent supervises the marketing team in read-only mode and research high level documentation status and bootstrap the marketing team with the necessary information to conduct the audit. The MarketingSupervisor will also step in to review the work of the marketing agents and ensure that it meets the standards of quality and relevance. It will request revisions or additional work from the marketing agents if necessary, and will provide feedback and guidance to ensure that the marketing audit is comprehensive and accurate.
- **MarketingAgent1-3**: These Sonnet agents are responsible for conducting the marketing audit tasks. They will focus on different aspects of the marketing audit, such as user documentation, ease of setup, packaging and distribution, and marketing materials. They will work in parallel to ensure a comprehensive audit of the marketing aspects of the project and report back to the team lead.
- **Feature Gap Analyst**: This Opus agent is responsible for conducting the feature gap analysis. It requires all previous research and marketing audit reports to conduct its analysis. It will identify any gaps in the project's features compared to competitors or user expectations, and will provide a detailed report on its findings. The Feature Gap Analyst will also provide recommendations for addressing any identified gaps, and will work with the marketing team to ensure that the project's value proposition is clear and compelling.

## Lifecycle

The team is to be kept alive, even after the audit is complete as the user might request new work or ask follow up questions. The team should be ready to respond to any new requests or questions from the user, and should continue to provide support and assistance as needed.
The team lead must never itself perform any heavy lifting and must instead only focus on managing the work and flow of the team, stepping in when agents are stuck, in loop or in need of further instructions. The team lead is the only agent that can communicate with the user and must ensure that all communication is clear, concise, and informative. The team lead is also responsible for ensuring that all agents are working effectively and efficiently, and that the overall goals of the audit are being met.
